# legacy：重构前的旧实现

这里的 6 个文件是重构前 `backend/` 根目录下的原始代码，**不参与运行**，仅作对照保留。

| 文件 | 旧职责 | 新位置 |
| --- | --- | --- |
| `main.py` | FastAPI 单文件应用，硬编码 `API_TOKEN` | `app/main.py` + `app/api/*` |
| `rag.py` | 上传/问答全部逻辑，PDF 整体拼接 | `app/services/document_service.py`、`app/services/chat_service.py` |
| `vector_stores.py` | Chroma 封装，`clean_text` 误删所有空格 | `app/services/vector_store.py`、`app/services/cleaning.py` |
| `knowledge_base.py` | `./chat_history/{session_id}` 裸文件存历史 | `app/services/conversation.py` + SQLite |
| `config_data.py` | 手写 os.getenv 读取配置 | `app/core/config.py`（pydantic-settings） |
| `check_db.py` | 旧向量库调试脚本 | `scripts/rebuild_index.py --stats` |

确认新实现稳定后可以整个目录删除。