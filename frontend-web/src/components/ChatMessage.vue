<script setup lang="ts">
import { ElMessage } from 'element-plus'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import java from 'highlight.js/lib/languages/java'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import python from 'highlight.js/lib/languages/python'
import sql from 'highlight.js/lib/languages/sql'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import MarkdownIt from 'markdown-it'
import { computed, ref } from 'vue'

import { fetchChunks } from '@/api/document'
import SourceCard from '@/components/SourceCard.vue'
import type { ChunkPreview, MessageItem, SourceItem } from '@/types'
import { formatDateTime } from '@/utils/format'

// 只注册常用语言，避免把 highlight.js 全量语言包（1MB+）打进产物
const LANGUAGES = { bash, java, javascript, json, python, sql, typescript, xml }
for (const [name, language] of Object.entries(LANGUAGES)) {
  hljs.registerLanguage(name, language)
}
hljs.registerAliases(['html', 'vue'], { languageName: 'xml' })
hljs.registerAliases(['sh', 'shell'], { languageName: 'bash' })
hljs.registerAliases(['js'], { languageName: 'javascript' })
hljs.registerAliases(['ts'], { languageName: 'typescript' })
hljs.registerAliases(['py'], { languageName: 'python' })

const props = defineProps<{ message: MessageItem }>()
// html:false 关闭内联 HTML，避免模型输出被当作标签执行
const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  highlight(code: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        const highlighted = hljs.highlight(code, { language: lang, ignoreIllegals: true }).value
        return `<pre class="hljs"><code>${highlighted}</code></pre>`
      } catch {
        // 高亮失败时退回纯转义
      }
    }
    return `<pre class="hljs"><code>${md.utils.escapeHtml(code)}</code></pre>`
  },
})

const isUser = computed(() => props.message.role === 'user')
const renderedHtml = computed(() => (isUser.value ? '' : md.render(props.message.content || '')))
const hasContent = computed(() => props.message.content.trim().length > 0)

// ===================== 来源抽屉 =====================

const drawerVisible = ref(false)
const activeSource = ref<SourceItem | null>(null)
const activeText = ref('')
const fullTextLoading = ref(false)
/** 同一文档的切片只拉一次，重复点开不同来源不再请求 */
const chunkCache = new Map<number, ChunkPreview[]>()

async function openSource(source: SourceItem): Promise<void> {
  activeSource.value = source
  activeText.value = source.snippet
  drawerVisible.value = true

  if (!source.doc_id) {
    return
  }

  fullTextLoading.value = true
  try {
    let chunks = chunkCache.get(source.doc_id)
    if (!chunks) {
      const result = await fetchChunks(source.doc_id)
      chunks = result.items
      chunkCache.set(source.doc_id, chunks)
    }
    const hit = chunks.find((item) => item.chunk_id === source.chunk_id)
    if (hit) {
      activeText.value = hit.text
    }
  } catch {
    // 拉不到全文就继续展示 snippet，不打断阅读
  } finally {
    fullTextLoading.value = false
  }
}

// ===================== 复制 =====================

async function copyAnswer(): Promise<void> {
  if (!hasContent.value) {
    return
  }
  try {
    await navigator.clipboard.writeText(props.message.content)
    ElMessage.success('已复制答案')
  } catch {
    ElMessage.warning('当前浏览器不允许自动复制，请手动选择文本')
  }
}

function scoreText(source: SourceItem): string {
  const parts: string[] = []
  if (source.rerank_score !== null && source.rerank_score !== undefined) {
    parts.push(`重排 ${source.rerank_score.toFixed(4)}`)
  }
  if (source.vector_score !== null && source.vector_score !== undefined) {
    parts.push(`向量 ${source.vector_score.toFixed(4)}`)
  }
  if (source.bm25_score !== null && source.bm25_score !== undefined) {
    parts.push(`BM25 ${source.bm25_score.toFixed(3)}`)
  }
  if (source.rrf_score !== null && source.rrf_score !== undefined) {
    parts.push(`RRF ${source.rrf_score.toFixed(5)}`)
  }
  return parts.length > 0 ? parts.join(' · ') : '无分数'
}
</script>

<template>
  <div class="message" :class="{ mine: isUser }">
    <div class="avatar">{{ isUser ? '我' : 'AI' }}</div>

    <div class="body">
      <!-- 用户消息按纯文本展示，保留换行即可 -->
      <div v-if="isUser" class="bubble user-bubble">{{ message.content }}</div>

      <div v-else class="bubble ai-bubble">
        <div v-if="hasContent" class="markdown-body" v-html="renderedHtml" />
        <div v-else-if="message.streaming" class="thinking">正在检索并组织答案…</div>

        <span v-if="message.streaming && hasContent" class="cursor" />

        <el-alert
          v-if="message.error"
          class="error"
          :title="message.error"
          type="error"
          :closable="false"
          show-icon
        />

        <div v-if="message.sources.length > 0" class="sources">
          <div class="sources-title">
            <span>引用来源 · {{ message.sources.length }} 条</span>
            <span class="hint">点击卡片查看完整片段</span>
          </div>
          <div class="source-grid">
            <SourceCard
              v-for="source in message.sources"
              :key="source.chunk_id"
              :source="source"
              @open="openSource"
            />
          </div>
        </div>

        <div v-if="!message.streaming" class="footer">
          <span class="meta">
            {{ formatDateTime(message.created_at) }}
            <template v-if="message.latency_ms"> · {{ message.latency_ms }}ms</template>
          </span>
          <el-button v-if="hasContent" link size="small" @click="copyAnswer">复制</el-button>
        </div>
      </div>
    </div>

    <el-drawer v-model="drawerVisible" size="520px" :title="activeSource?.filename || '来源片段'">
      <div v-if="activeSource" class="drawer-body">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="引用编号">[{{ activeSource.index }}]</el-descriptions-item>
          <el-descriptions-item label="文件">{{ activeSource.filename }}</el-descriptions-item>
          <el-descriptions-item label="页码">
            {{ activeSource.page ? `第 ${activeSource.page} 页` : '该格式无页码' }}
          </el-descriptions-item>
          <el-descriptions-item label="章节">
            {{ activeSource.section || '未识别章节' }}
          </el-descriptions-item>
          <el-descriptions-item label="chunk_id">
            {{ activeSource.chunk_id }}
          </el-descriptions-item>
          <el-descriptions-item label="得分">{{ scoreText(activeSource) }}</el-descriptions-item>
        </el-descriptions>

        <div class="drawer-text">
          <div class="drawer-text-head">
            <span>片段原文</span>
            <span v-if="fullTextLoading" class="loading">正在加载完整片段…</span>
          </div>
          <pre>{{ activeText }}</pre>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.message {
  display: flex;
  gap: 12px;
  padding: 4px 0 18px;
}

.message.mine {
  flex-direction: row-reverse;
}

.avatar {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  margin-top: 2px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #3a6ff7, #6a9cff);
  border-radius: 9px;
}

.message.mine .avatar {
  color: #4a5261;
  background: #e6eaf2;
}

.body {
  max-width: 82%;
  min-width: 0;
}

.message.mine .body {
  display: flex;
  justify-content: flex-end;
  max-width: 70%;
}

.bubble {
  padding: 12px 16px;
  font-size: 14px;
  border-radius: 12px;
}

.user-bubble {
  color: #fff;
  white-space: pre-wrap;
  background: var(--rag-primary);
  border-bottom-right-radius: 3px;
}

.ai-bubble {
  background: var(--rag-panel);
  border: 1px solid var(--rag-border);
  border-bottom-left-radius: 3px;
}

.thinking {
  font-size: 13px;
  color: var(--rag-text-weak);
}

.cursor {
  display: inline-block;
  width: 6px;
  height: 15px;
  margin-left: 2px;
  vertical-align: text-bottom;
  background: var(--rag-primary);
  animation: blink 1s steps(2, start) infinite;
}

@keyframes blink {
  to {
    visibility: hidden;
  }
}

.error {
  margin-top: 10px;
}

.sources {
  padding-top: 12px;
  margin-top: 12px;
  border-top: 1px dashed var(--rag-border);
}

.sources-title {
  display: flex;
  gap: 10px;
  align-items: baseline;
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #4a5261;
}

.sources-title .hint {
  font-weight: 400;
  color: var(--rag-text-weak);
}

.source-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 8px;
}

.footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}

.meta {
  font-size: 11px;
  color: var(--rag-text-weak);
}

.drawer-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.drawer-text-head {
  display: flex;
  gap: 10px;
  align-items: baseline;
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 600;
}

.loading {
  font-size: 11px;
  font-weight: 400;
  color: var(--rag-text-weak);
}

.drawer-text pre {
  max-height: 60vh;
  padding: 12px 14px;
  margin: 0;
  overflow: auto;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 13px;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
  background: #f7f8fa;
  border-radius: 8px;
}
</style>