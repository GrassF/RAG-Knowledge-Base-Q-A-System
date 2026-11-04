/**
 * SSE 流式问答客户端。
 *
 * 为什么不用浏览器原生 EventSource：
 * 1. 它只能发 GET，而问答需要 POST 携带问题与检索参数；
 * 2. 它无法自行控制请求头与中断，这里用 fetch + ReadableStream 手写解析。
 */
import { onScopeDispose, ref } from 'vue'

import { API_BASE_URL, ApiError } from '@/api/http'
import type {
  ChatRequestPayload,
  SseDelta,
  SseDone,
  SseError,
  SseMeta,
  SseSources,
} from '@/types'

export interface StreamHandlers {
  onMeta?: (payload: SseMeta) => void
  onSources?: (payload: SseSources) => void
  onDelta?: (payload: SseDelta) => void
  onDone?: (payload: SseDone) => void
  onError?: (payload: SseError) => void
}

interface RawFrame {
  event: string
  data: string
}

/**
 * 解析一帧 SSE 文本（不含结尾空行）。
 * 格式：`event: xxx\ndata: {...}`，多行 data 按协议用 \n 拼接。
 */
function parseFrame(frame: string): RawFrame | null {
  let event = 'message'
  const dataLines: string[] = []

  for (const line of frame.split('\n')) {
    if (!line || line.startsWith(':')) {
      continue
    }
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice('data:'.length).replace(/^ /, ''))
    }
  }

  if (dataLines.length === 0) {
    return null
  }
  return { event, data: dataLines.join('\n') }
}

function dispatch(frame: string, handlers: StreamHandlers): void {
  const parsed = parseFrame(frame)
  if (!parsed) {
    return
  }

  let body: unknown
  try {
    body = JSON.parse(parsed.data)
  } catch {
    // 脏帧直接丢弃，不影响后续事件
    return
  }

  switch (parsed.event) {
    case 'meta':
      handlers.onMeta?.(body as SseMeta)
      break
    case 'sources':
      handlers.onSources?.(body as SseSources)
      break
    case 'delta':
      handlers.onDelta?.(body as SseDelta)
      break
    case 'done':
      handlers.onDone?.(body as SseDone)
      break
    case 'error':
      handlers.onError?.(body as SseError)
      break
    default:
      break
  }
}

/** 读取非 2xx 响应体里的统一错误包装，转成 ApiError */
async function toApiError(response: Response): Promise<ApiError> {
  const text = await response.text().catch(() => '')
  let code = response.status
  let message = `请求失败（HTTP ${response.status}）`

  if (text) {
    try {
      const body = JSON.parse(text) as { code?: number; message?: string }
      if (typeof body.code === 'number') {
        code = body.code
      }
      if (body.message) {
        message = body.message
      }
    } catch {
      // 非 JSON（例如网关的 HTML 错误页），保留默认文案
    }
  }
  return new ApiError(code, message)
}

/** 发起一次问答请求，按事件回调把增量数据交给调用方 */
export async function streamChat(
  payload: ChatRequestPayload,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  }

  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    signal,
  })

  if (!response.ok) {
    throw await toApiError(response)
  }
  if (!response.body) {
    throw new ApiError(5000, '当前浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) {
        break
      }
      // 统一换行，避免 \r\n 导致空行切分失效
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')

      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        dispatch(buffer.slice(0, boundary), handlers)
        buffer = buffer.slice(boundary + 2)
        boundary = buffer.indexOf('\n\n')
      }
    }
    // 服务端未以空行结尾时的残留帧
    if (buffer.trim()) {
      dispatch(buffer, handlers)
    }
  } finally {
    try {
      await reader.cancel()
    } catch {
      // 已正常关闭，忽略
    }
  }
}

/** 组件内使用的便捷封装：持有 AbortController，卸载时自动中断 */
export function useSSE() {
  const isStreaming = ref(false)
  let controller: AbortController | null = null

  function abort(): void {
    if (controller) {
      controller.abort()
      controller = null
    }
    isStreaming.value = false
  }

  async function send(payload: ChatRequestPayload, handlers: StreamHandlers): Promise<void> {
    abort()
    controller = new AbortController()
    isStreaming.value = true
    try {
      await streamChat(payload, handlers, controller.signal)
    } finally {
      controller = null
      isStreaming.value = false
    }
  }

  onScopeDispose(abort)

  return { isStreaming, send, abort }
}