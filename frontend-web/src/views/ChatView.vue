<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, nextTick, onMounted, ref, watch } from 'vue'

import { extractErrorMessage } from '@/api/http'
import ChatMessage from '@/components/ChatMessage.vue'
import ConversationSidebar from '@/components/ConversationSidebar.vue'
import RetrievalPanel from '@/components/RetrievalPanel.vue'
import { useChatStore } from '@/stores/chat'
import { useConversationStore } from '@/stores/conversation'

const chat = useChatStore()
const conversations = useConversationStore()

const draft = ref('')
const scrollRef = ref<HTMLElement>()
/** 用户向上翻阅历史时不要被强行拉回底部 */
const stickToBottom = ref(true)

const canSend = computed(() => draft.value.trim().length > 0 && !chat.streaming)

const statusHint = computed(() => {
  if (chat.streaming) {
    return '正在生成，可随时中断'
  }
  if (chat.searchQuery) {
    return `本次检索 query：${chat.searchQuery}`
  }
  if (chat.lastLatency) {
    return `上一轮耗时 ${chat.lastLatency}ms`
  }
  return '回答中的 [1][2] 与下方来源卡片一一对应'
})

onMounted(async () => {
  // 从其它页面返回时，沿用当前选中的会话并重新拉取历史；没有选中则开一个新对话
  if (conversations.activeId) {
    await handleSelect(conversations.activeId)
    return
  }
  chat.clear({ abort: false })
})

function handleCreate(): void {
  chat.clear()
  draft.value = ''
}

async function handleSelect(conversationId: string): Promise<void> {
  try {
    await chat.loadHistory(conversationId)
    stickToBottom.value = true
    await nextTick()
    const el = scrollRef.value
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  }
}

async function handleSend(): Promise<void> {
  if (!canSend.value) {
    return
  }
  const question = draft.value.trim()
  draft.value = ''
  stickToBottom.value = true
  await chat.send(question)
}

function handleScroll(): void {
  const el = scrollRef.value
  if (!el) {
    return
  }
  stickToBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

// 流式输出时逐字跟随滚动
watch(
  () => chat.messages.map((item) => item.content).join(''),
  async () => {
    if (!stickToBottom.value) {
      return
    }
    await nextTick()
    const el = scrollRef.value
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  },
)
</script>

<template>
  <div class="chat-view">
    <ConversationSidebar @create="handleCreate" @select="handleSelect" />

    <section class="chat-main">
      <div ref="scrollRef" class="chat-scroll" @scroll.passive="handleScroll">
        <div class="chat-inner">
          <div v-if="chat.loadingHistory" class="loading">正在加载历史消息…</div>

          <div v-else-if="chat.messages.length === 0" class="welcome">
            <h2>基于知识库回答，并标注每一句的出处</h2>
            <p>
              先去
              <router-link to="/documents" class="link">知识库</router-link>
              上传 PDF / DOCX / TXT，再回来提问。
            </p>
            <ul>
              <li>切分会保留页码与章节，来源卡片可以直接跳回原文位置</li>
              <li>默认使用「向量 + BM25」混合召回，勾选重排可进一步提升精度</li>
              <li>展开底部「检索参数」可以在提问前调整 Top-K、阈值与重排开关</li>
            </ul>
          </div>

          <ChatMessage v-for="item in chat.messages" :key="item.id" :message="item" />
        </div>
      </div>

      <div class="chat-composer">
        <RetrievalPanel />

        <el-input
          v-model="draft"
          class="input"
          type="textarea"
          :rows="3"
          resize="none"
          maxlength="2000"
          show-word-limit
          placeholder="输入你的问题，Enter 发送，Shift + Enter 换行"
          @keydown.enter.exact.prevent="handleSend"
        />

        <div class="composer-actions">
          <span class="hint">{{ statusHint }}</span>
          <div class="buttons">
            <el-button v-if="chat.streaming" @click="chat.stop()">停止生成</el-button>
            <el-button type="primary" :loading="chat.streaming" :disabled="!canSend" @click="handleSend">
              发送
            </el-button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.chat-view {
  display: flex;
  height: 100%;
  overflow: hidden;
}

.chat-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  height: 100%;
}

.chat-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.chat-inner {
  max-width: 900px;
  padding: 24px 24px 8px;
  margin: 0 auto;
}

.loading {
  padding: 40px 0;
  font-size: 13px;
  color: var(--rag-text-weak);
  text-align: center;
}

.welcome {
  padding: 40px 32px;
  background: var(--rag-panel);
  border: 1px solid var(--rag-border);
  border-radius: 14px;
}

.welcome h2 {
  margin: 0 0 10px;
  font-size: 20px;
  font-weight: 600;
}

.welcome p {
  margin: 0 0 16px;
  font-size: 14px;
  color: var(--rag-text-weak);
}

.welcome ul {
  padding-left: 18px;
  margin: 0;
  font-size: 13px;
  line-height: 2;
  color: #4a5261;
}

.link {
  font-weight: 600;
  color: var(--rag-primary);
}

.chat-composer {
  flex-shrink: 0;
  padding: 0 24px 16px;
  background: var(--rag-bg);
  border-top: 1px solid var(--rag-border);
}

.chat-composer .input {
  margin-top: 10px;
}

.composer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}

.hint {
  overflow: hidden;
  font-size: 12px;
  color: var(--rag-text-weak);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.buttons {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  margin-left: 12px;
}

/* 让输入区与消息区宽度对齐 */
@media (width >= 1000px) {
  .chat-composer {
    padding-right: max(24px, calc((100% - 900px) / 2));
    padding-left: max(24px, calc((100% - 900px) / 2));
  }
}
</style>