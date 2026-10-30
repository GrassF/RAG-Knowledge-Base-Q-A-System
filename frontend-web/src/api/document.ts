/** 文档管理与健康检查接口 */
import { request } from './http'
import type {
  ChunkPreviewOut,
  ClearResult,
  DocumentItem,
  HealthInfo,
  UploadResult,
} from '@/types'

export function listDocuments(): Promise<DocumentItem[]> {
  return request<DocumentItem[]>({ url: '/documents', method: 'get' })
}

export function uploadDocument(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<UploadResult> {
  const form = new FormData()
  form.append('file', file)
  return request<UploadResult>({
    url: '/documents/upload',
    method: 'post',
    data: form,
    onUploadProgress: (event) => {
      if (!onProgress || !event.total) return
      onProgress(Math.round((event.loaded / event.total) * 100))
    },
  })
}

export function fetchChunks(docId: number): Promise<ChunkPreviewOut> {
  return request<ChunkPreviewOut>({ url: `/documents/${docId}/chunks`, method: 'get' })
}

export function deleteDocument(docId: number): Promise<{ doc_id: number; deleted_chunks: number }> {
  return request({ url: `/documents/${docId}`, method: 'delete' })
}

export function clearDocuments(): Promise<ClearResult> {
  return request<ClearResult>({ url: '/documents/clear', method: 'post' })
}

export function fetchHealth(): Promise<HealthInfo> {
  return request<HealthInfo>({ url: '/health', method: 'get' })
}