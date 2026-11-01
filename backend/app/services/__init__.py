"""业务服务层：所有 RAG 编排逻辑都在这里。

问答链路（建议按此顺序阅读）：
    container → chat_service → rag_chain → hybrid_retriever
    → vector_store / bm25_index / reranker
入库链路：
    document_service → parser/* → splitter → embedding → vector_store
"""
