/** 问答与会话管理接口 */
import { request } from './http'
import type { ConversationDetail, ConversationItem } from '@/types'

export function listConversations(): Promise<ConversationItem[]> {
  return request<ConversationItem[]>({ url: '/chat/conversations', method: 'get' })
}

export function fetchConversation(conversationId: string): Promise<ConversationDetail> {
  return request<ConversationDetail>({
    url: `/chat/conversations/${conversationId}/messages`,
    method: 'get',
  })
}

export function renameConversation(
  conversationId: string,
  title: string,
): Promise<ConversationItem> {
  return request<ConversationItem>({
    url: `/chat/conversations/${conversationId}`,
    method: 'patch',
    data: { title },
  })
}

export function deleteConversation(conversationId: string): Promise<null> {
  return request<null>({
    url: `/chat/conversations/${conversationId}`,
    method: 'delete',
  })
}