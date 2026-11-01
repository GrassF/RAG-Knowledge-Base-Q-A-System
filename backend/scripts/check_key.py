"""API Key 与入口域名连通性自检。

只读 .env 里的 Key，不会打印 Key 本身。用来回答两件事：
1. Key 是否有效；
2. 对话 / 向量化 / 重排三个模型是否都能调通，以及该用哪个入口域名。

用法（在 backend/ 目录下执行）：

    # 用配置里的公共域名（dashscope.aliyuncs.com）测试
    python scripts/check_key.py

    # 用控制台给你的工作空间专属域名测试
    python scripts/check_key.py --base-url https://ws-xxxx.cn-beijing.maas.aliyuncs.com/api/v1

两个都跑一遍：哪个通过就说明你的 Key 认哪个入口。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许从 backend/ 目录直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dashscope  # noqa: E402
import requests  # noqa: E402

from app.core.config import get_settings  # noqa: E402

RERANK_PATH = "/services/rerank/text-rerank/text-rerank"


def _report(name: str, fn) -> bool:
    try:
        detail = fn()
    except Exception as exc:  # 自检脚本要吞掉异常，只报结论
        message = str(exc).replace("\n", " ")[:300]
        print(f"  [FAIL] {name}: {type(exc).__name__}: {message}")
        return False
    print(f"  [OK]   {name}: {detail}")
    return True


def check_chat(model: str) -> str:
    from langchain_community.chat_models.tongyi import ChatTongyi

    llm = ChatTongyi(model=model, dashscope_api_key=KEY, streaming=False)
    content = str(llm.invoke("只回答两个字：你好").content)
    return f"模型 {model} 返回 {content[:40]!r}"


def check_embedding(model: str) -> str:
    from langchain_community.embeddings import DashScopeEmbeddings

    client = DashScopeEmbeddings(model=model, dashscope_api_key=KEY)
    vector = client.embed_query("连通性测试")
    return f"模型 {model} 返回 {len(vector)} 维向量"


def check_rerank(model: str, base_url: str) -> str:
    response = requests.post(
        f"{base_url.rstrip('/')}{RERANK_PATH}",
        headers={"Authorization": f"Bearer {KEY}"},
        json={
            "model": model,
            "input": {"query": "病假工资怎么算", "documents": ["病假工资按 60% 发放", "年假工资照常发放"]},
            "parameters": {"return_documents": False, "top_n": 2},
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
    results = (response.json().get("output") or {}).get("results") or []
    return f"模型 {model} 返回 {len(results)} 条评分"


def main() -> int:
    global KEY

    parser = argparse.ArgumentParser(description="DashScope API Key 连通性自检")
    parser.add_argument("--base-url", default=None, help="入口地址，默认取配置里的 dashscope_base_url")
    args = parser.parse_args()

    settings = get_settings()
    KEY = settings.dashscope_api_key

    if not KEY or KEY == "xxx":
        print("DASHSCOPE_API_KEY 未配置：请先在 backend/.env 中填入真实 Key")
        return 1

    base_url = (args.base_url or settings.dashscope_base_url).rstrip("/")
    # 对话与向量化都读这个 SDK 全局变量，必须先设置再创建 client
    dashscope.base_http_api_url = base_url

    print(f"入口: {base_url}")
    print(f"Key : 已配置（长度 {len(KEY)}，前缀 {KEY[:3]}***）")
    print()

    results = [
        _report("对话", lambda: check_chat(settings.chat_model_name)),
        _report("向量化", lambda: check_embedding(settings.embedding_model_name)),
        _report("重排", lambda: check_rerank(settings.rerank_model, base_url)),
    ]

    print()
    passed = sum(results)
    print(f"结果: {passed}/{len(results)} 通过")
    if passed == len(results):
        print("该入口可用，无需修改代码。")
    elif passed == 0:
        print("该入口完全不可用：换另一个入口（公共域名 / 专属域名）再试一次。")
    else:
        print("部分模型不可用：可能是该模型未开通，也可能是入口不匹配。")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
