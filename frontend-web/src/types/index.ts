/** 与后端 app/schemas 一一对应的类型定义。改动后端字段时同步这里。 */

/** 统一响应包装：code=0 表示成功，非 0 见后端 ErrorCode */
export interface ApiResponse<T> {
  code: number
  message: string
  data: T | null
  request_id?: string | null
}

// ===================== 检索 =====================

export type RetrievalMode = 'vector' | 'bm25' | 'hybrid'

/** 检索参数覆盖，未传的字段后端用配置默认值 */
export interface RetrievalOptions {
  mode?: RetrievalMode
  top_k?: number
  vector_top_k?: number
  bm25_top_k?: number
  score_threshold?: number
  use_rerank?: boolean
  rerank_top_n?: number
}

/** 引用来源：回答里 [1] 对应的一条检索片段 */
export interface SourceItem {
  index: number
  chunk_id: string
  doc_id: number | null
  filename: string
  page: number | null
  section: string | null
  snippet: string
  vector_score: number | null
  bm25_score: number | null
  rrf_score: number | null
  rerank_score: number | null
}

// ===================== 会话 =====================

export type ChatRole = 'user' | 'assistant'

export interface MessageItem {
  id: string
  role: ChatRole
  content: string
  sources: SourceItem[]
  created_at: string
  /** 前端本地状态：该条消息是否正在流式输出 */
  streaming?: boolean
  /** 前端本地状态：流式过程中的错误提示 */
  error?: string | null
  /** 前端本地状态：本轮问答耗时 */
  latency_ms?: number | null
}

export interface ConversationItem {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface ConversationDetail {
  conversation: ConversationItem
  messages: MessageItem[]
}

// ===================== 文档 =====================

export interface DocumentItem {
  id: number
  filename: string
  file_size: number
  file_type: string
  status: string
  chunk_count: number
  error_message: string | null
  created_at: string
}

export interface UploadResult {
  doc_id: number
  filename: string
  chunk_count: number
  page_count: number
  section_count: number
  status: string
  duplicated: boolean
  message: string
}

export interface ChunkPreview {
  chunk_id: string
  chunk_index: number
  page: number | null
  section: string | null
  char_start: number
  char_end: number
  text: string
}

export interface ChunkPreviewOut {
  doc_id: number
  filename: string
  total: number
  items: ChunkPreview[]
}

export interface ClearResult {
  deleted_documents: number
  deleted_chunks: number
  message: string
}

export interface HealthInfo {
  status: string
  version: string
  vector_type: string
  collection: string
  vectors: number
  bm25_chunks: number
  retrieval_mode: RetrievalMode
  rerank_model: string | null
}

// ===================== SSE 事件负载 =====================

export interface SseMeta {
  conversation_id: string
  title: string
}

export interface SseSources {
  sources: SourceItem[]
  search_query: string
}

export interface SseDelta {
  text: string
}

export interface SseDone {
  message_id: string
  conversation_id: string
  conversation_title: string
  latency_ms: number
  source_count: number
}

export interface SseError {
  code: number
  message: string
}

/** 一次问答请求体 */
export interface ChatRequestPayload {
  question: string
  conversation_id?: string | null
  retrieval?: RetrievalOptions
}