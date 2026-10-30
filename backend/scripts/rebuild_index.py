"""索引维护脚本。

用法（在 backend/ 目录下执行）：

    # 1. 从向量库重建 BM25 索引（常见场景：手工改过切片、索引文件损坏）
    python scripts/rebuild_index.py

    # 2. 查看统计
    python scripts/rebuild_index.py --stats

    # 3. 把旧版 collection 的数据迁移到新结构（会重新向量化）
    python scripts/rebuild_index.py --migrate-legacy --username demo

    # 4. 迁移前先演练，只打印数量不写库
    python scripts/rebuild_index.py --migrate-legacy --username demo --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import uuid
from pathlib import Path

# 允许直接 python scripts/xxx.py 运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.config import BASE_DIR, get_settings  # noqa: E402
from app.db.database import session_scope  # noqa: E402
from app.db.init_db import init_db  # noqa: E402
from app.db.models import Document, User  # noqa: E402
from app.services.splitter import Chunk  # noqa: E402

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


def migrate_legacy(
    legacy_dir: Path, legacy_collection: str, username: str, dry_run: bool
) -> None:
    """把旧版（rag）collection 的切片导入新 collection 与 BM25 索引。

    旧数据的 metadata 只有 source/create_time/operator，没有页码，
    因此迁移后 page/section 为空，需要页码追溯的文档建议重新上传原件。
    """
    from langchain_chroma import Chroma

    from app.services.container import get_rag

    if not legacy_dir.exists():
        raise SystemExit(f"旧向量库目录不存在：{legacy_dir}")

    legacy = Chroma(
        collection_name=legacy_collection,
        persist_directory=str(legacy_dir),
        embedding_function=None,  # 只读，不需要 embedding
    )
    data = legacy.get()
    documents = data.get("documents") or []
    metadatas = data.get("metadatas") or []
    if not documents:
        print("旧 collection 为空，无需迁移")
        return

    grouped: dict[str, list[str]] = {}
    for text, meta in zip(documents, metadatas):
        source = (meta or {}).get("source") or "unknown"
        grouped.setdefault(source, []).append(text or "")

    print(f"发现旧切片 {len(documents)} 条，涉及文件 {len(grouped)} 个")
    if dry_run:
        for name, texts in grouped.items():
            print(f"  - {name}：{len(texts)} 片")
        print("--dry-run：未写入任何数据")
        return

    init_db()
    with session_scope() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            raise SystemExit(f"用户 {username} 不存在，请先在系统里注册")

        rag = get_rag()
        total = 0
        for filename, texts in grouped.items():
            joined = "\n".join(texts)
            file_hash = hashlib.sha256(joined.encode("utf-8")).hexdigest()
            existing = db.scalar(
                select(Document).where(
                    Document.user_id == user.id, Document.file_hash == file_hash
                )
            )
            if existing is not None:
                print(f"  跳过（已存在）：{filename}")
                continue

            document = Document(
                user_id=user.id,
                filename=filename,
                file_hash=file_hash,
                file_size=len(joined.encode("utf-8")),
                file_type=Path(filename).suffix.lower(),
                status="processing",
            )
            db.add(document)
            db.flush()

            chunks = [
                Chunk(
                    chunk_id=uuid.uuid4().hex,
                    text=text,
                    metadata={
                        "doc_id": document.id,
                        "user_id": user.id,
                        "filename": filename,
                        "file_type": document.file_type,
                        "chunk_index": index,
                        "kind": "paragraph",
                        "char_start": 0,
                        "char_end": len(text),
                        "create_time": "migrated",
                        "embedding_model": settings.embedding_model_name,
                    },
                )
                for index, text in enumerate(texts)
                if text.strip()
            ]
            rag.vector_store.add_chunks(chunks)
            rag.bm25_index.add_chunks(chunks)

            document.status = "ready"
            document.chunk_count = len(chunks)
            total += len(chunks)
            print(f"  已迁移：{filename}（{len(chunks)} 片）")

        print(f"迁移完成，共写入 {total} 个切片")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 知识库索引维护")
    parser.add_argument("--stats", action="store_true", help="只打印统计信息")
    parser.add_argument(
        "--migrate-legacy", action="store_true", help="迁移旧 collection 的数据到新结构"
    )
    parser.add_argument(
        "--legacy-dir",
        default=str(BASE_DIR / "chroma_db"),
        help="旧向量库目录（默认 backend/chroma_db）",
    )
    parser.add_argument("--legacy-collection", default="rag", help="旧 collection 名称（默认 rag）")
    parser.add_argument("--username", default="", help="迁移数据归属的用户名")
    parser.add_argument("--dry-run", action="store_true", help="只演练不写库")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    if args.migrate_legacy:
        if not args.username:
            raise SystemExit("迁移必须指定 --username")
        migrate_legacy(
            Path(args.legacy_dir), args.legacy_collection, args.username, args.dry_run
        )
        return

    rebuild_bm25()
    show_stats()


if __name__ == "__main__":
    main()