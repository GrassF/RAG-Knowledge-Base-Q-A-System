/** 会话列表状态：切换、重命名、删除，以及问答过程中新建会话的即时插入 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { deleteConversation, listConversations, renameConversation } from '@/api/chat'
import type { ConversationItem } from '@/types'

export const useConversationStore = defineStore('conversation', () => {
  const items = ref<ConversationItem[]>([])
  const activeId = ref<string | null>(null)
  const loading = ref(false)

  async function load(silent = false): Promise<void> {
    if (!silent) {
      loading.value = true
    }
    try {
      items.value = await listConversations()
    } finally {
      if (!silent) {
        loading.value = false
      }
    }
  }

  function setActive(conversationId: string | null): void {
    activeId.value = conversationId
  }

  /** 点"新建对话"时只是取消选中，真正的会话记录等首轮提问后由后端创建 */
  function startNew(): void {
    activeId.value = null
  }

  /** 流式问答收到 meta 事件后调用：把新会话插到列表顶部，或更新已有会话标题 */
  function upsertFromStream(conversationId: string, title: string): void {
    activeId.value = conversationId
    const existing = items.value.find((item) => item.id === conversationId)
    if (existing) {
      existing.title = title
      return
    }
    const stamp = new Date().toISOString()
    items.value.unshift({
      id: conversationId,
      title,
      created_at: stamp,
      updated_at: stamp,
      message_count: 0,
    })
  }

  function touch(conversationId: string): void {
    const index = items.value.findIndex((item) => item.id === conversationId)
    if (index === -1) {
      return
    }
    const [target] = items.value.splice(index, 1)
    target.updated_at = new Date().toISOString()
    items.value.unshift(target)
  }

  async function rename(conversationId: string, title: string): Promise<void> {
    const updated = await renameConversation(conversationId, title)
    const target = items.value.find((item) => item.id === conversationId)
    if (target) {
      target.title = updated.title
      target.updated_at = updated.updated_at
    }
  }

  async function remove(conversationId: string): Promise<void> {
    await deleteConversation(conversationId)
    items.value = items.value.filter((item) => item.id !== conversationId)
    if (activeId.value === conversationId) {
      activeId.value = null
    }
  }

  function reset(): void {
    items.value = []
    activeId.value = null
  }

  return {
    items,
    activeId,
    loading,
    load,
    setActive,
    startNew,
    upsertFromStream,
    touch,
    rename,
    remove,
    reset,
  }
})