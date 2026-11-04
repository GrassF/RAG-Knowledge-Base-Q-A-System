# RAG 知识库智能问答系统

基于 **FastAPI + LangChain + Chroma + 通义千问** 的知识库问答系统，前端为 **Vue 3 + TypeScript + Element Plus**。

系统围绕文档解析、检索质量与答案可追溯性构建完整链路：结构感知切分、混合检索、Cross-Encoder 重排、答案来源追溯到页码、统一异常与结构化日志。

## 核心能力

| 环节 | 实现 |
| --- | --- |
| 文档解析 | PDF 按页解析并剔除页眉页脚；DOCX 保留标题层级与表格；TXT 自动探测编码 |
| 文本清洗 | 只做规范化，保留空格与换行（避免破坏英文/代码语义），修复行尾连字符断词 |
| 切分 | `ParsedBlock(page, section)` 内部切分，天然不跨页、不跨章节；相邻短块按同页同章节合并 |
| 向量检索 | Chroma cosine 距离 + 相似度阈值过滤 + Top-K 可调 |
| 关键词检索 | jieba 搜索模式分词 + BM25Okapi，索引持久化到 JSON 并支持增量增删 |
| 混合检索 | 向量与 BM25 并行召回，用 RRF（`score = Σ 1/(k + rank)`，k=60）融合 |
| 重排序 | DashScope Cross-Encoder（`gte-rerank-v2`，可切 `qwen3-rerank`），超时自动降级 |
| 答案追溯 | SSE 先推 `sources` 再推答案，每条引用带文件名 / 页码 / 章节 / 各路分数 |
| 多轮对话 | SQLite 持久化会话与消息，历史按轮数裁剪 |
| 工程化 | pydantic-settings 配置、统一 `{code, message, data, request_id}`、loguru 结构化日志、可选限流 |

## 目录结构

```
backend/
├── app/
│   ├── main.py                # 应用工厂：中间件、路由、异常处理、生命周期
│   ├── core/                  # 配置 / 日志 / 异常码 / 中间件
│   ├── db/                    # SQLAlchemy 2.0 模型与会话
│   ├── schemas/               # Pydantic 请求响应模型
│   ├── api/                   # chat / documents / health 路由
│   └── services/
│       ├── parser/            # PDF / DOCX / TXT 解析，产出带页码章节的 ParsedBlock
│       ├── cleaning.py        # 文本清洗
│       ├── splitter.py        # 结构感知切分
│       ├── embedding.py       # DashScope Embedding（批量 + 重试）
│       ├── vector_store.py    # Chroma 封装
│       ├── bm25_index.py      # jieba + rank_bm25，JSON 持久化
│       ├── hybrid_retriever.py# 双路召回 + RRF 融合
│       ├── reranker.py        # DashScope / Qwen 两种重排实现
│       ├── rag_chain.py       # LCEL 链 + 编号引用 Prompt
│       ├── conversation.py    # 会话与消息持久化
│       ├── chat_service.py    # SSE 事件编排
│       └── document_service.py# 上传编排：解析→清洗→切分→入库→BM25
├── data/                      # app.db / chroma_db / index / logs（不入库）
├── scripts/                   # rebuild_index.py / smoke_test.py
├── tests/                     # 清洗、切分、RRF 的单元测试
├── .env.example
└── requirements.txt

frontend-web/
├── src/
│   ├── api/                   # http 封装 + 各业务接口
│   ├── composables/useSSE.ts  # fetch + ReadableStream 手写 SSE 解析
│   ├── stores/                # conversation / chat
│   ├── views/                 # ChatView / DocumentsView
│   └── components/            # ChatMessage / SourceCard / ConversationSidebar / RetrievalPanel
└── vite.config.ts             # /api 代理到 127.0.0.1:8000
```

## 快速开始

### 1. 后端

```bash
cd backend

# 建议使用虚拟环境
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt

# 配置 API Key
copy .env.example .env          # 然后填入真实的 DASHSCOPE_API_KEY

uvicorn app.main:app --reload --port 8000
```

启动后可访问：

- 接口文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/v1/health>

### 2. 前端

```bash
cd frontend-web
npm install
npm run dev          # http://localhost:5173
```

开发环境由 Vite 把 `/api` 代理到 `http://127.0.0.1:8000`，因此前端代码里统一使用相对路径，不需要额外处理跨域。

## 接口一览

所有接口统一返回 `{ code, message, data, request_id }`，`code = 0` 表示成功。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/chat/stream` | SSE 流式问答 |
| GET | `/api/v1/chat/conversations` | 会话列表 |
| GET | `/api/v1/chat/conversations/{id}/messages` | 历史消息（含引用来源） |
| PATCH | `/api/v1/chat/conversations/{id}` | 重命名会话 |
| DELETE | `/api/v1/chat/conversations/{id}` | 删除会话 |
| POST | `/api/v1/documents/upload` | 上传文档（TXT / PDF / DOCX，≤ 20MB） |
| GET | `/api/v1/documents` | 文档列表 |
| GET | `/api/v1/documents/{id}/chunks` | 切片预览（调参用） |
| DELETE | `/api/v1/documents/{id}` | 删除文档（同步清理向量与 BM25） |
| POST | `/api/v1/documents/clear` | 清空知识库 |
| GET | `/api/v1/health` | 健康检查 |

### SSE 事件顺序

问答接口返回 `text/event-stream`，前端按事件类型渲染：

```
event: meta      -> {"conversation_id":"...","title":"..."}
event: sources   -> {"sources":[{"index":1,"filename":"产品手册.pdf","page":3,
                                "section":"第2章 > 2.1","snippet":"...","rerank_score":0.87}]}
event: delta     -> {"text":"向量"}
event: done      -> {"message_id":"...","latency_ms":1840}
event: error     -> {"code":5002,"message":"重排服务超时，已降级"}
```

先推 `sources` 再推 `delta`，是为了让引用卡片在答案开始输出前就已经就位。

### 检索参数覆盖

`POST /chat/stream` 的 `retrieval` 字段可覆盖默认检索配置，未传的项回落到 `.env`：

```json
{
  "question": "系统采用什么检索策略？",
  "conversation_id": null,
  "retrieval": {
    "mode": "hybrid",
    "top_k": 5,
    "vector_top_k": 20,
    "bm25_top_k": 20,
    "score_threshold": 0.3,
    "use_rerank": true,
    "rerank_top_n": 5
  }
}
```

前端「检索参数」面板即是这套参数的可视化，方便实时对比纯向量 / 纯 BM25 / 混合的效果差异。

## 测试与验证

```bash
# 单元测试：清洗、切分、RRF 融合（纯函数，不需要 API Key）
cd backend
python -m pytest tests -q

# 端到端冒烟：上传 -> 问答 -> 来源校验 -> 会话历史 -> 删除 -> 清空
# 需要后端已启动且 DASHSCOPE_API_KEY 可用
python scripts/smoke_test.py
python scripts/smoke_test.py --pdf D:/docs/手册.pdf   # 额外验证 PDF 页码

# 索引维护
python scripts/rebuild_index.py --stats
python scripts/rebuild_index.py                       # 从向量库重建 BM25
```

## 技术栈

- **后端**：FastAPI、SQLAlchemy 2.0、pydantic-settings、loguru
- **检索**：LangChain、Chroma、jieba + rank_bm25、RRF
- **模型**：阿里百炼（qwen3-max / text-embedding-v4 / gte-rerank-v2）
- **前端**：Vue 3、TypeScript、Vite、Pinia、Element Plus
