/**
 * 问答状态机。
 *
 * 一次提问的渲染顺序与后端 SSE 事件严格对应：
 *   推送用户消息 -> 占位助手消息 -> meta(落会话) -> sources(来源卡片)
 *   -> delta(逐字追加) -> done(补真实 message_id 与耗时)
 */
import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'

import { fetchConversation } from '@/api/chat'
import { extractErrorMessage } from '@/api/http'
import { useSSE } from '@/composables/useSSE'
import { useConversationStore } from '@/stores/conversation'
import type { MessageItem, RetrievalMode, RetrievalOptions } from '@/types'

/** 检索面板可调参数 */
export interface RetrievalForm {
  mode: RetrievalMode
  top_k: number
  vector_top_k: number
  bm25_top_k: number
  score_threshold: number
  use_rerank: boolean
  rerank_top_n: number
}

/** 与后端 Settings 默认值保持一致，"重置"即回到服务端配置 */
export const DEFAULT_RETRIEVAL: RetrievalForm = {
  mode: 'hybrid',
  top_k: 5,
  vector_top_k: 20,
  bm25_top_k: 20,
  score_threshold: 0,
  use_rerank: true,
  rerank_top_n: 5,
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<MessageItem[]>([])
  const loadingHistory = ref(false)
  const searchQuery = ref('')
  const lastLatency = ref<number | null>(null)
  const errorMessage = ref('')
  const retrieval = reactive<RetrievalForm>({ ...DEFAULT_RETRIEVAL })
  const sse = useSSE()

  const streaming = sse.isStreaming

  function resetRetrieval(): void {
    Object.assign(retrieval, DEFAULT_RETRIEVAL)
  }

  function buildRetrievalOptions(): RetrievalOptions {
    return {
      mode: retrieval.mode,
      top_k: retrieval.top_k,
      vector_top_k: retrieval.vector_top_k,
      bm25_top_k: retrieval.bm25_top_k,
      score_threshold: retrieval.score_threshold,
      use_rerank: retrieval.use_rerank,
      rerank_top_n: retrieval.rerank_top_n,
    }
  }

  function clear(options: { abort?: boolean } = {}): void {
    if (options.abort !== false) {
      sse.abort()
    }
    messages.value = []
    searchQuery.value = ''
    lastLatency.value = null
    errorMessage.value = ''
  }

  function stop(): void {
    sse.abort()
  }

  async function loadHistory(conversationId: string): Promise<void> {
    clear()
    loadingHistory.value = true
    try {
      const detail = await fetchConversation(conversationId)
      messages.value = detail.messages
    } finally {
      loadingHistory.value = false
    }
  }

  async function send(rawQuestion: string): Promise<void> {
    const question = rawQuestion.trim()
    if (!question || streaming.value) {
      return
    }

    const conversations = useConversationStore()
    const conversationId = conversations.activeId

    const stamp = new Date().toISOString()
    messages.value.push(
      reactive<MessageItem>({
        id: `local-user-${Date.now()}`,
        role: 'user',
        content: question,
        sources: [],
        created_at: stamp,
      }),
    )

    const assistant = reactive<MessageItem>({
      id: `local-assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      sources: [],
      created_at: stamp,
      streaming: true,
      error: null,
      latency_ms: null,
    })
    messages.value.push(assistant)

    searchQuery.value = ''
    lastLatency.value = null
    errorMessage.value = ''

    try {
      await sse.send(
        {
          question,
          conversation_id: conversationId,
          retrieval: buildRetrievalOptions(),
        },
        {
          onMeta: (meta) => {
            conversations.upsertFromStream(meta.conversation_id, meta.title)
          },
          onSources: (payload) => {
            assistant.sources = payload.sources
            searchQuery.value = payload.search_query
          },
          onDelta: (payload) => {
            assistant.content += payload.text
          },
          onDone: (payload) => {
            assistant.id = payload.message_id
            assistant.latency_ms = payload.latency_ms
            lastLatency.value = payload.latency_ms
            conversations.upsertFromStream(payload.conversation_id, payload.conversation_title)
            conversations.touch(payload.conversation_id)
            // 静默刷新会话列表，让 message_count 与后端一致
            void conversations.load(true).catch(() => undefined)
          },
          onError: (payload) => {
            assistant.error = payload.message
            errorMessage.value = payload.message
          },
        },
      )
    } catch (error) {
      if (isAbortError(error)) {
        assistant.error = '已停止生成'
      } else {
        assistant.error = extractErrorMessage(error)
        errorMessage.value = assistant.error
      }
    } finally {
      assistant.streaming = false
    }
  }

  return {
    messages,
    loadingHistory,
    searchQuery,
    lastLatency,
    errorMessage,
    retrieval,
    streaming,
    resetRetrieval,
    buildRetrievalOptions,
    clear,
    stop,
    loadHistory,
    send,
  }
})