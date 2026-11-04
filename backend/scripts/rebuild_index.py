"""索引维护脚本。

用法（在 backend/ 目录下执行）：

    # 1. 从向量库重建 BM25 索引（常见场景：手工改过切片、索引文件损坏）
    python scripts/rebuild_index.py

    # 2. 只看统计，不写索引
    python scripts/rebuild_index.py --stats
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许直接 python scripts/xxx.py 运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402

settings = get_settings()


def show_stats() -> None:
    from app.services.container import get_rag

    rag = get_rag()
    print("=" * 60)
    print(f"向量库        : {settings.vector_type} / {settings.collection_name}")
    print(f"向量数量      : {rag.vector_store.count()}")
    print(f"BM25 切片数   : {rag.bm25_index.size}")
    print(f"索引文件      : {settings.bm25_index_path}")
    print(f"检索模式      : {settings.retrieval_mode}")
    print(f"重排模型      : {settings.rerank_model if settings.use_rerank else '未启用'}")
    print("=" * 60)


def rebuild_bm25() -> None:
    from app.services.container import get_rag

    rag = get_rag()
    documents = rag.vector_store.all_documents()
    if not documents:
        print("向量库为空，无需重建")
        return
    count = rag.bm25_index.rebuild_from_documents(documents)
    print(f"BM25 索引重建完成：{count} 个切片")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 知识库索引维护")
    parser.add_argument("--stats", action="store_true", help="只打印统计信息")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    rebuild_bm25()
    show_stats()


if __name__ == "__main__":
    main()
