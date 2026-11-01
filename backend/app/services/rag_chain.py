"""RAG 问答链：检索 → 组装带编号的参考资料 → 调用大模型流式生成。

核心约束：SYSTEM_PROMPT 强制「只依据参考资料作答、引用必须标注 [n]、
          资料不足时直接回答未找到」，以此抑制模型编造
主要方法：retrieve() 检索；stream_answer() 流式生成；rewrite_query() 指代消解
位置：ChatService → 本文件 → HybridRetriever + ChatTongyi
注意：检索为空时不短路，仍会调用模型，只是上下文里塞入占位提示
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from loguru import logger

from app.core.config import Settings, get_settings
from app.schemas.chat import RetrievalOptions
from app.services.bm25_index import BM25Index
from app.services.embedding import EmbeddingService
from app.services.hybrid_retriever import HybridRetriever
from app.services.reranker import create_reranker
from app.services.retrieval_types import RetrievedChunk
from app.services.vector_store import VectorStoreService

SYSTEM_PROMPT = """你是严谨的知识库问答助手，只能依据下面的「参考资料」回答问题，禁止编造。

回答规则：
1. 参考资料带编号，引用某条资料时，必须在相应句子末尾标注编号，例如：向量检索使用余弦相似度 [1][3]。
2. 回答中的具体数据、条款、结论必须能在参考资料中找到出处。
3. 参考资料不足以回答时，直接回答"知识库中未找到相关内容"，并说明还需要补充哪方面信息。
4. 若多条资料互相矛盾，请分别指出并标注各自的编号。
5. 不要写"根据参考资料"这类空话，直接给结论；使用 Markdown 组织答案。

参考资料：
{context}"""

NO_CONTEXT_PLACEHOLDER = "（本次未检索到相关资料）"


class RagChain:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

        self.embedding = EmbeddingService(self.settings)
        self.vector_store = VectorStoreService(self.embedding, self.settings)
        self.bm25_index = BM25Index(self.settings.bm25_index_path)
        self.retriever = HybridRetriever(
            vector_store=self.vector_store,
            bm25_index=self.bm25_index,
            reranker=create_reranker(self.settings),
            settings=self.settings,
        )

        self.chat_model = ChatTongyi(
            model=self.settings.chat_model_name,
            dashscope_api_key=self.settings.dashscope_api_key or None,
            temperature=self.settings.llm_temperature,
            streaming=True,
        )
        self.prompt_template = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                ("system", "以下是用户与你的历史对话，注意指代关系："),
                MessagesPlaceholder("history", optional=True),
                ("human", "{question}"),
            ]
        )
        # LCEL：Prompt -> 模型 -> 纯文本
        self.answer_chain = self.prompt_template | self.chat_model | StrOutputParser()

    # ===================== 索引准备 =====================
    def ensure_bm25_ready(self) -> None:
        """启动时调用：优先读缓存，缺失则从向量库全量重建。"""
        BM25Index.warm_up()
        if self.bm25_index.load():
            return
        documents = self.vector_store.all_documents()
        if documents:
            self.bm25_index.rebuild_from_documents(documents)
        else:
            logger.info("向量库为空，跳过 BM25 索引重建")

    def refresh_bm25_from_store(self) -> int:
        """索引文件损坏或与向量库不一致时的强制重建。"""
        return self.bm25_index.rebuild_from_documents(self.vector_store.all_documents())

    # ===================== 检索 =====================
    def retrieve(
        self, question: str, options: RetrievalOptions | None = None
    ) -> list[RetrievedChunk]:
        return self.retriever.retrieve(question, options)

    # ===================== 生成 =====================
    @staticmethod
    def format_context(chunks: Sequence[RetrievedChunk]) -> str:
        if not chunks:
            return NO_CONTEXT_PLACEHOLDER
        blocks: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            blocks.append(f"[{index}] 来源：{chunk.location()}\n{chunk.text.strip()}")
        return "\n\n".join(blocks)

    def build_inputs(
        self, question: str, chunks: Sequence[RetrievedChunk], history: Sequence[BaseMessage]
    ) -> dict[str, Any]:
        return {
            "context": self.format_context(chunks),
            "history": list(history),
            "question": question,
        }

    def stream_answer(
        self, question: str, chunks: Sequence[RetrievedChunk], history: Sequence[BaseMessage]
    ) -> Iterator[str]:
        """流式产出答案 token。"""
        inputs = self.build_inputs(question, chunks, history)
        try:
            for delta in self.answer_chain.stream(inputs):
                if delta:
                    yield delta
        except Exception as exc:
            logger.exception("大模型流式调用失败")
            raise

    def answer(
        self, question: str, chunks: Sequence[RetrievedChunk], history: Sequence[BaseMessage]
    ) -> str:
        inputs = self.build_inputs(question, chunks, history)
        return self.answer_chain.invoke(inputs)

    # ===================== 指代消解（可选） =====================
    def rewrite_query(self, question: str, history: Sequence[BaseMessage]) -> str:
        """把"它多少钱"这类追问改写成可独立检索的查询。

        默认关闭：多一次大模型调用会明显增加首字延迟，
        只有在多轮对话质量确实受指代影响时才打开。
        """
        if not self.settings.enable_query_rewrite or not history:
            return question

        recent = history[-4:]
        transcript = "\n".join(
            f"{'用户' if message.type == 'human' else '助手'}：{message.content[:300]}"
            for message in recent
        )
        rewrite_chain = (
            ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "你是查询改写助手。根据对话历史，把用户的最新问题改写成一个语义完整、"
                        "可独立用于检索的问题。只输出改写后的问题本身，不要解释。",
                    ),
                    ("human", "对话历史：\n{transcript}\n\n最新问题：{question}"),
                ]
            )
            | ChatTongyi(
                model=self.settings.query_rewrite_model,
                dashscope_api_key=self.settings.dashscope_api_key or None,
                temperature=0.0,
                streaming=False,
            )
            | StrOutputParser()
        )
        try:
            rewritten = rewrite_chain.invoke({"transcript": transcript, "question": question}).strip()
        except Exception as exc:
            logger.warning("查询改写失败，使用原始问题：{}", exc)
            return question

        rewritten = rewritten.splitlines()[0].strip() if rewritten else ""
        if not rewritten or len(rewritten) > 500:
            return question
        logger.info("查询改写：{} -> {}", question, rewritten)
        return rewritten
