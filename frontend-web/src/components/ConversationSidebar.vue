<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted } from 'vue'

import { extractErrorMessage } from '@/api/http'
import { useConversationStore } from '@/stores/conversation'
import type { ConversationItem } from '@/types'
import { formatRelativeTime } from '@/utils/format'

const emit = defineEmits<{ select: [id: string]; create: [] }>()

const conversations = useConversationStore()

onMounted(async () => {
  try {
    await conversations.load()
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  }
})

function handleCreate(): void {
  conversations.startNew()
  emit('create')
}

function handleSelect(item: ConversationItem): void {
  if (conversations.activeId === item.id) {
    return
  }
  conversations.setActive(item.id)
  emit('select', item.id)
}

async function handleRename(item: ConversationItem): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入新的会话名称', '重命名会话', {
      inputValue: item.title,
      inputValidator: (input: string) => (input && input.trim() ? true : '名称不能为空'),
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    await conversations.rename(item.id, value.trim())
    ElMessage.success('已重命名')
  } catch (error) {
    if (error === 'cancel' || error === 'close') {
      return
    }
    ElMessage.error(extractErrorMessage(error))
  }
}

async function handleRemove(item: ConversationItem): Promise<void> {
  try {
    await ElMessageBox.confirm(`删除会话「${item.title}」？该操作不可恢复。`, '删除会话', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await conversations.remove(item.id)
    ElMessage.success('会话已删除')
    if (conversations.activeId === null) {
      emit('create')
    }
  } catch (error) {
    if (error === 'cancel' || error === 'close') {
      return
    }
    ElMessage.error(extractErrorMessage(error))
  }
}
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-head">
      <span class="title">会话</span>
      <el-button type="primary" size="small" @click="handleCreate">新建对话</el-button>
    </div>

    <el-scrollbar class="sidebar-list">
      <el-empty v-if="!conversations.loading && conversations.items.length === 0" description="还没有会话" :image-size="70" />

      <ul v-else class="list">
        <li
          v-for="item in conversations.items"
          :key="item.id"
          class="item"
          :class="{ active: conversations.activeId === item.id }"
          @click="handleSelect(item)"
        >
          <div class="item-main">
            <span class="item-title" :title="item.title">{{ item.title }}</span>
            <span class="item-meta">
              {{ item.message_count }} 条 · {{ formatRelativeTime(item.updated_at) }}
            </span>
          </div>

          <div class="item-actions" @click.stop>
            <el-button link size="small" @click="handleRename(item)">改名</el-button>
            <el-button link size="small" type="danger" @click="handleRemove(item)">删除</el-button>
          </div>
        </li>
      </ul>
    </el-scrollbar>
  </aside>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  width: 264px;
  flex-shrink: 0;
  height: 100%;
  background: var(--rag-panel);
  border-right: 1px solid var(--rag-border);
}

.sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 14px 12px;
}

.title {
  font-size: 13px;
  font-weight: 600;
  color: var(--rag-text-weak);
}

.sidebar-list {
  flex: 1;
  min-height: 0;
  padding: 0 8px 12px;
}

.list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 10px;
  margin-bottom: 4px;
  cursor: pointer;
  border-radius: 8px;
  transition: background 0.15s ease;
}

.item:hover {
  background: #f4f6fa;
}

.item.active {
  background: #eef3ff;
}

.item-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 3px;
}

.item-title {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item.active .item-title {
  font-weight: 600;
  color: var(--rag-primary);
}

.item-meta {
  font-size: 11px;
  color: var(--rag-text-weak);
}

.item-actions {
  flex-shrink: 0;
  visibility: hidden;
}

.item:hover .item-actions {
  visibility: visible;
}
</style>