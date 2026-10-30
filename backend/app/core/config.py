"""全局配置。

所有配置集中在这里，通过 .env 或环境变量覆盖，禁止在业务代码里硬编码。
配置对象只创建一次（lru_cache），避免重复读取磁盘。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录：app/core/config.py -> core -> app -> backend
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """应用配置。

    字段名的小写形式即环境变量名，例如 dashscope_api_key 对应 DASHSCOPE_API_KEY。
    """

    model_config = SettingsConfigDict(
        env_file=(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===================== 应用 =====================
    app_name: str = "RAG 知识库智能问答系统"
    app_version: str = "2.0.0"
    api_prefix: str = "/api/v1"
    debug: bool = False
    port: int = 8000

    # 允许跨域的前端地址，逗号分隔
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ===================== 模型（阿里百炼） =====================
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    # qwen3-rerank 走 OpenAI 兼容端点，与上面的标准端点不同
    dashscope_compatible_base_url: str = "https://dashscope.aliyuncs.com/compatible-api/v1"

    chat_model_name: str = "qwen3-max"
    embedding_model_name: str = "text-embedding-v4"
    # DashScope embedding 单次请求文本条数上限较小，按批提交
    embedding_batch_size: int = 10
    llm_temperature: float = 0.3

    # ===================== 数据存储 =====================
    data_dir: str = "./data"
    sqlite_filename: str = "app.db"

    # ===================== 向量库 =====================
    vector_type: str = "chroma"
    collection_name: str = "rag_v2"
    persist_directory: str = "./data/chroma_db"
    # PGVector 配置（vector_type=pgvector 时生效）
    pg_connection_string: str = ""
    pg_collection_name: str = "rag_v2"

    # ===================== 文档切分 =====================
    chunk_size: int = 500
    chunk_overlap: int = 80
    min_chunk_size: int = 120

    # ===================== 检索 =====================
    # vector | bm25 | hybrid
    retrieval_mode: str = "hybrid"
    # 双路召回各自的候选数
    vector_top_k: int = 20
    bm25_top_k: int = 20
    # 融合 + 重排后最终送入 Prompt 的条数
    final_top_k: int = 5
    # RRF 平滑常数
    rrf_k: int = 60
    # 向量相似度阈值（cosine relevance，0 表示不过滤）
    score_threshold: float = 0.0

    # ===================== 重排 =====================
    use_rerank: bool = True
    # gte-rerank-v2 走标准 DashScope 端点，qwen3-rerank 走 OpenAI 兼容端点
    rerank_model: str = "gte-rerank-v2"
    rerank_top_n: int = 5
    rerank_timeout: float = 3.0

    # ===================== 多轮对话 =====================
    max_history_rounds: int = 10
    max_message_chars: int = 2000
    # 指代消解：用历史把追问改写成独立查询，多一次大模型调用
    enable_query_rewrite: bool = False
    query_rewrite_model: str = "qwen3-max"

    # ===================== 鉴权 =====================
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # ===================== 上传限制 =====================
    max_upload_size_mb: int = 20
    allowed_extensions: str = ".txt,.pdf,.docx"

    # ===================== 限流（可选） =====================
    rate_limit_enabled: bool = False
    rate_limit_per_minute: int = 30

    # ===================== 日志 =====================
    log_level: str = "INFO"
    log_dir: str = "./data/logs"

    @field_validator("retrieval_mode")
    @classmethod
    def _check_mode(cls, value: str) -> str:
        allowed = {"vector", "bm25", "hybrid"}
        value = value.strip().lower()
        if value not in allowed:
            raise ValueError(f"retrieval_mode 必须是 {allowed} 之一")
        return value

    @field_validator("chunk_size", "chunk_overlap", "min_chunk_size")
    @classmethod
    def _check_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("切分参数必须为正整数")
        return value

    # ===================== 派生路径 =====================
    @property
    def data_path(self) -> Path:
        return self._resolve(self.data_dir)

    @property
    def sqlite_path(self) -> Path:
        return self.data_path / self.sqlite_filename

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.sqlite_path.as_posix()}"

    @property
    def chroma_path(self) -> Path:
        return self._resolve(self.persist_directory)

    @property
    def bm25_index_path(self) -> Path:
        return self.data_path / "index" / f"bm25_{self.collection_name}.json"

    @property
    def log_path(self) -> Path:
        return self._resolve(self.log_dir)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def allowed_extension_list(self) -> list[str]:
        return [item.strip().lower() for item in self.allowed_extensions.split(",") if item.strip()]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @staticmethod
    def _resolve(raw: str) -> Path:
        """相对路径统一以 backend/ 为基准，避免不同启动目录导致数据分裂。"""
        path = Path(raw)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
