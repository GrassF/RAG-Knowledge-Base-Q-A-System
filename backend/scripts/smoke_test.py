"""端到端冒烟测试。

前置条件：
1. 后端已启动：uvicorn app.main:app --port 8000
2. backend/.env 里配置了真实可用的 DASHSCOPE_API_KEY

用法（在 backend/ 目录下执行）：

    python scripts/smoke_test.py
    python scripts/smoke_test.py --base-url http://127.0.0.1:8000/api/v1
    python scripts/smoke_test.py --pdf D:/docs/手册.pdf     # 额外验证 PDF 页码

它会覆盖：健康检查 -> 注册/登录 -> 上传 DOCX -> 查看切片 -> SSE 问答
-> 会话历史 -> 删除文档 -> 跨用户隔离 -> 清空。
每一步失败都会立刻退出并打印原因。
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import uuid
from pathlib import Path

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"


class SmokeError(RuntimeError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)
    print(f"  [OK] {message}")


class Client:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None
        self.session = requests.Session()
        self.session.timeout = 120

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _handle(self, response: requests.Response) -> dict:
        try:
            payload = response.json()
        except ValueError:
            raise SmokeError(f"响应不是合法 JSON（HTTP {response.status_code}）：{response.text[:300]}")
        if payload.get("code") != 0:
            raise SmokeError(
                f"接口返回错误（HTTP {response.status_code}）："
                f"code={payload.get('code')} message={payload.get('message')}"
            )
        return payload["data"]

    def get(self, path: str) -> dict:
        return self._handle(self.session.get(self.base_url + path, headers=self.headers()))

    def post(self, path: str, **kwargs) -> dict:
        return self._handle(
            self.session.post(self.base_url + path, headers=self.headers(), **kwargs)
        )

    def patch(self, path: str, **kwargs) -> dict:
        return self._handle(
            self.session.patch(self.base_url + path, headers=self.headers(), **kwargs)
        )

    def delete(self, path: str) -> dict:
        return self._handle(self.session.delete(self.base_url + path, headers=self.headers()))


def build_sample_docx() -> bytes:
    """生成一份带标题层级和表格的 DOCX，用来验证 section 与表格解析。"""
    from docx import Document as DocxDocument

    document = DocxDocument()
    document.add_heading("第一章 系统概述", level=1)
    document.add_paragraph("本系统用于验证文档解析、切分与来源追溯能力。")
    document.add_paragraph("知识库支持 PDF、DOCX、TXT 三种格式，并保留页码与章节信息。")

    document.add_heading("1.1 检索策略", level=2)
    document.add_paragraph(
        "系统采用向量检索与 BM25 关键词检索双路召回，再通过 RRF 融合排序。"
        "该策略在包含精确术语的问题上明显优于单一向量检索。"
    )
    table = document.add_table(rows=3, cols=2)
    table.cell(0, 0).text = "参数"
    table.cell(0, 1).text = "默认值"
    table.cell(1, 0).text = "chunk_size"
    table.cell(1, 1).text = "500"
    table.cell(2, 0).text = "rrf_k"
    table.cell(2, 1).text = "60"

    document.add_heading("1.2 重排序", level=2)
    document.add_paragraph(
        "初步召回后使用 Cross-Encoder 重排序模型对候选片段打分，取分数最高的若干条进入提示词。"
    )

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def iter_sse(response: requests.Response):
    """解析 SSE 事件流，产出 (event, data_str)。"""
    event = "message"
    data_lines: list[str] = []
    for raw in response.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        if raw == "":
            if data_lines:
                yield event, "\n".join(data_lines)
            event, data_lines = "message", []
            continue
        if raw.startswith("event:"):
            event = raw[len("event:") :].strip()
        elif raw.startswith("data:"):
            data_lines.append(raw[len("data:") :].lstrip())
    if data_lines:
        yield event, "\n".join(data_lines)


def run(base_url: str, pdf_path: Path | None) -> None:
    suffix = uuid.uuid4().hex[:6]
    user_a = f"smoke_a_{suffix}"
    user_b = f"smoke_b_{suffix}"
    password = "SmokeTest123"

    print("\n[1] 健康检查")
    anon = Client(base_url)
    health = anon.get("/health")
    check(health["status"] == "ok", f"服务正常，向量数={health['vectors']}")

    print("\n[2] 注册两个用户（用于验证会话隔离）")
    client_a = Client(base_url)
    token_a = client_a.post("/auth/register", json={"username": user_a, "password": password})
    client_a.token = token_a["access_token"]
    check(bool(client_a.token), f"用户 {user_a} 注册成功")

    client_b = Client(base_url)
    token_b = client_b.post("/auth/register", json={"username": user_b, "password": password})
    client_b.token = token_b["access_token"]
    check(bool(client_b.token), f"用户 {user_b} 注册成功")

    me = client_a.get("/auth/me")
    check(me["username"] == user_a, "获取当前用户信息正常")

    print("\n[3] 上传 DOCX 并检查结构信息")
    files = {
        "file": (
            "冒烟测试文档.docx",
            build_sample_docx(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    upload = client_a.post("/documents/upload", files=files)
    doc_id = upload["doc_id"]
    check(upload["chunk_count"] > 0, f"切片数 = {upload['chunk_count']}")
    check(upload["section_count"] > 0, f"识别章节数 = {upload['section_count']}")

    chunks = client_a.get(f"/documents/{doc_id}/chunks")
    check(chunks["total"] == upload["chunk_count"], "切片预览数量与入库数量一致")
    check(
        any(item["section"] for item in chunks["items"]),
        "切片带有 section 元数据",
    )

    documents = client_a.get("/documents")
    check(len(documents) == 1, "文档列表返回 1 条")

    if pdf_path is not None:
        print(f"\n[3.1] 额外验证 PDF 页码：{pdf_path}")
        pdf_upload = client_a.post(
            "/documents/upload", files={"file": (pdf_path.name, pdf_path.read_bytes())}
        )
        pdf_chunks = client_a.get(f"/documents/{pdf_upload['doc_id']}/chunks")
        check(
            any(item["page"] for item in pdf_chunks["items"]),
            "PDF 切片带有页码",
        )

    print("\n[4] 流式问答并校验来源")
    question = "系统采用什么检索策略？重排序是怎么做的？"
    payload = {
        "question": question,
        "retrieval": {"mode": "hybrid", "top_k": 4, "use_rerank": True},
    }
    events: list[str] = []
    sources: list[dict] = []
    answer = ""
    meta: dict = {}
    done: dict = {}

    with client_a.session.post(
        client_a.base_url + "/chat/stream", json=payload, headers=client_a.headers(), stream=True
    ) as response:
        check(response.status_code == 200, "SSE 接口返回 200")
        for event, data in iter_sse(response):
            events.append(event)
            body = json.loads(data) if data else {}
            if event == "meta":
                meta = body
            elif event == "sources":
                sources = body.get("sources", [])
            elif event == "delta":
                answer += body.get("text", "")
            elif event == "done":
                done = body
            elif event == "error":
                raise SmokeError(f"问答返回错误事件：{body}")

    check("meta" in events and "sources" in events and "done" in events, f"事件顺序 = {events[:5]}...")
    check(len(sources) > 0, f"引用来源 {len(sources)} 条")
    check(bool(sources[0]["filename"]), f"来源文件名 = {sources[0]['filename']}")
    check(len(answer.strip()) > 0, f"答案长度 = {len(answer)}")
    check(bool(done.get("message_id")), "done 事件带回 message_id")

    conversation_id = meta["conversation_id"]

    print("\n[5] 会话历史与引用持久化")
    conversations = client_a.get("/chat/conversations")
    check(len(conversations) == 1, "会话列表返回 1 条")
    detail = client_a.get(f"/chat/conversations/{conversation_id}/messages")
    check(len(detail["messages"]) == 2, "历史包含 1 问 1 答")
    check(
        len(detail["messages"][1]["sources"]) > 0,
        "助手消息的引用来源已持久化",
    )

    renamed = client_a.patch(
        f"/chat/conversations/{conversation_id}", json={"title": "冒烟测试会话"}
    )
    check(renamed["title"] == "冒烟测试会话", "会话重命名成功")

    print("\n[6] 跨用户隔离")
    other_conversations = client_b.get("/chat/conversations")
    check(other_conversations == [], "用户 B 看不到用户 A 的会话")

    forbidden = client_b.session.get(
        client_b.base_url + f"/chat/conversations/{conversation_id}/messages",
        headers=client_b.headers(),
    )
    check(forbidden.status_code == 404, "用户 B 访问用户 A 的会话返回 404")

    other_documents = client_b.get("/documents")
    check(other_documents == [], "用户 B 看不到用户 A 的文档")

    print("\n[7] 删除文档并校验索引清理")
    deleted = client_a.delete(f"/documents/{doc_id}")
    check(deleted["deleted_chunks"] > 0, f"清理向量 {deleted['deleted_chunks']} 条")
    check(client_a.get("/documents") == [], "文档列表已清空")

    print("\n[8] 清空知识库")
    cleared = client_a.post("/documents/clear")
    check(cleared["deleted_documents"] == 0, "清空操作幂等（此时已无文档）")

    print("\n全部冒烟检查通过")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 知识库端到端冒烟测试")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--pdf", default=None, help="可选：额外验证一个真实 PDF 的页码")
    args = parser.parse_args()

    try:
        run(args.base_url, Path(args.pdf) if args.pdf else None)
    except SmokeError as exc:
        print(f"\n[FAIL] {exc}")
        sys.exit(1)
    except requests.RequestException as exc:
        print(f"\n[FAIL] 请求失败，确认后端是否已启动：{exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()