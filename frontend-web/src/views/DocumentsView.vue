<script setup lang="ts">
import { ElMessage, ElMessageBox, type UploadRawFile, type UploadRequestOptions } from 'element-plus'
import { onMounted, ref } from 'vue'

import {
  clearDocuments,
  deleteDocument,
  fetchChunks,
  fetchHealth,
  listDocuments,
  uploadDocument,
} from '@/api/document'
import { extractErrorMessage } from '@/api/http'
import type { ChunkPreview, DocumentItem, HealthInfo } from '@/types'
import { formatDateTime, formatFileSize } from '@/utils/format'

const ALLOWED_EXTENSIONS = ['.txt', '.pdf', '.docx']
const MAX_SIZE = 20 * 1024 * 1024

const documents = ref<DocumentItem[]>([])
const health = ref<HealthInfo | null>(null)
const loading = ref(false)
const uploading = ref(false)
const progress = ref(0)

const chunkDrawer = ref(false)
const chunkLoading = ref(false)
const chunkTitle = ref('')
const chunks = ref<ChunkPreview[]>([])
const chunkTotal = ref(0)

const STATUS_LABELS: Record<string, string> = {
  ready: '已就绪',
  processing: '处理中',
  failed: '失败',
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status
}

function statusType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'ready') {
    return 'success'
  }
  if (status === 'processing') {
    return 'warning'
  }
  if (status === 'failed') {
    return 'danger'
  }
  return 'info'
}

async function loadDocuments(): Promise<void> {
  loading.value = true
  try {
    documents.value = await listDocuments()
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  } finally {
    loading.value = false
  }
}

async function loadHealth(): Promise<void> {
  try {
    health.value = await fetchHealth()
  } catch {
    // 健康信息只是辅助展示，失败不打扰用户
    health.value = null
  }
}

onMounted(async () => {
  await Promise.all([loadDocuments(), loadHealth()])
})

/** 前端先做一次类型/大小校验，省掉一次无谓的请求 */
function beforeUpload(file: UploadRawFile): boolean {
  const name = file.name.toLowerCase()
  if (!ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    ElMessage.error(`仅支持 ${ALLOWED_EXTENSIONS.join(' / ')} 格式`)
    return false
  }
  if (file.size > MAX_SIZE) {
    ElMessage.error('文件不能超过 20MB')
    return false
  }
  return true
}

async function handleUpload(options: UploadRequestOptions): Promise<void> {
  uploading.value = true
  progress.value = 0
  try {
    const result = await uploadDocument(options.file, (percent) => {
      progress.value = percent
    })
    if (result.duplicated) {
      ElMessage.info(result.message)
    } else {
      ElMessage.success(
        `${result.filename} 已入库：${result.chunk_count} 个切片 / ` +
          `${result.page_count} 页 / ${result.section_count} 个章节`,
      )
    }
    await Promise.all([loadDocuments(), loadHealth()])
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  } finally {
    uploading.value = false
    progress.value = 0
  }
}

async function openChunks(document: DocumentItem): Promise<void> {
  chunkTitle.value = `${document.filename}（共 ${document.chunk_count} 片）`
  chunks.value = []
  chunkTotal.value = 0
  chunkDrawer.value = true
  chunkLoading.value = true
  try {
    const result = await fetchChunks(document.id)
    chunks.value = result.items
    chunkTotal.value = result.total
  } catch (error) {
    ElMessage.error(extractErrorMessage(error))
  } finally {
    chunkLoading.value = false
  }
}

async function handleDelete(document: DocumentItem): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `删除「${document.filename}」会同时清理向量库与 BM25 索引，确认继续？`,
      '删除文档',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    const result = await deleteDocument(document.id)
    ElMessage.success(`已删除，清理 ${result.deleted_chunks} 个切片`)
    await Promise.all([loadDocuments(), loadHealth()])
  } catch (error) {
    if (error === 'cancel' || error === 'close') {
      return
    }
    ElMessage.error(extractErrorMessage(error))
  }
}

async function handleClear(): Promise<void> {
  if (documents.value.length === 0) {
    ElMessage.info('知识库已经是空的')
    return
  }
  try {
    await ElMessageBox.confirm('清空后当前账号的所有文档与索引都会被删除，确认继续？', '清空知识库', {
      type: 'warning',
      confirmButtonText: '清空',
      cancelButtonText: '取消',
    })
    const result = await clearDocuments()
    ElMessage.success(`已清空 ${result.deleted_documents} 个文档 / ${result.deleted_chunks} 个切片`)
    await Promise.all([loadDocuments(), loadHealth()])
  } catch (error) {
    if (error === 'cancel' || error === 'close') {
      return
    }
    ElMessage.error(extractErrorMessage(error))
  }
}
</script>

<template>
  <div class="documents-view">
    <el-scrollbar>
      <div class="page">
        <header class="page-head">
          <div>
            <h2>知识库</h2>
            <p>上传的文档会被解析成带页码与章节的切片，同时写入向量库和 BM25 索引。</p>
          </div>
          <el-button type="danger" plain :disabled="documents.length === 0" @click="handleClear">
            清空知识库
          </el-button>
        </header>

        <div v-if="health" class="health">
          <el-tag type="success" effect="plain">服务正常 v{{ health.version }}</el-tag>
          <el-tag type="info" effect="plain">向量库 {{ health.vector_type }}/{{ health.collection }}</el-tag>
          <el-tag type="info" effect="plain">向量 {{ health.vectors }}</el-tag>
          <el-tag type="info" effect="plain">BM25 {{ health.bm25_chunks }}</el-tag>
          <el-tag type="info" effect="plain">默认模式 {{ health.retrieval_mode }}</el-tag>
          <el-tag type="info" effect="plain">
            重排 {{ health.rerank_model || '未启用' }}
          </el-tag>
        </div>

        <el-upload
          class="uploader"
          drag
          multiple
          :show-file-list="false"
          :before-upload="beforeUpload"
          :http-request="handleUpload"
          :disabled="uploading"
          accept=".txt,.pdf,.docx"
        >
          <div class="upload-text">
            <p class="upload-title">把文件拖到这里，或点击选择</p>
            <p class="upload-tip">支持 PDF / DOCX / TXT，单个文件不超过 20MB</p>
          </div>
        </el-upload>

        <el-progress
          v-if="uploading"
          class="progress"
          :percentage="progress"
          :status="progress >= 100 ? 'success' : undefined"
        />
        <p v-if="uploading && progress >= 100" class="progress-tip">
          正在解析并向量化，大文件可能需要几十秒…
        </p>

        <el-table v-loading="loading" :data="documents" class="table" row-key="id">
          <el-table-column prop="filename" label="文件名" min-width="240" show-overflow-tooltip />
          <el-table-column label="类型" width="90">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ row.file_type || '-' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="100">
            <template #default="{ row }">{{ formatFileSize(row.file_size) }}</template>
          </el-table-column>
          <el-table-column prop="chunk_count" label="切片数" width="90" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tooltip
                :content="row.error_message || statusLabel(row.status)"
                placement="top"
                :disabled="!row.error_message"
              >
                <el-tag size="small" :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="上传时间" width="160">
            <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <el-button link size="small" @click="openChunks(row)">切片</el-button>
              <el-button link size="small" type="danger" @click="handleDelete(row)">删除</el-button>
            </template>
          </el-table-column>

          <template #empty>
            <el-empty description="知识库还是空的，先上传一份文档吧" :image-size="90" />
          </template>
        </el-table>
      </div>
    </el-scrollbar>

    <el-drawer v-model="chunkDrawer" :title="chunkTitle" size="620px">
      <div v-loading="chunkLoading" class="chunk-list">
        <p class="chunk-summary">共 {{ chunkTotal }} 个切片，展示前 {{ chunks.length }} 个</p>
        <div v-for="chunk in chunks" :key="chunk.chunk_id" class="chunk">
          <div class="chunk-head">
            <span class="chunk-index">#{{ chunk.chunk_index }}</span>
            <el-tag v-if="chunk.page" size="small" effect="plain" type="info">
              第 {{ chunk.page }} 页
            </el-tag>
            <el-tag v-if="chunk.section" size="small" effect="plain" type="info">
              {{ chunk.section }}
            </el-tag>
            <span class="chunk-range">{{ chunk.char_start }} - {{ chunk.char_end }} 字符</span>
          </div>
          <pre class="chunk-text">{{ chunk.text }}</pre>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.documents-view {
  height: 100%;
}

.page {
  max-width: 1180px;
  padding: 28px 24px 48px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 18px;
}

.page-head h2 {
  margin: 0 0 6px;
  font-size: 20px;
}

.page-head p {
  margin: 0;
  font-size: 13px;
  color: var(--rag-text-weak);
}

.health {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 18px;
}

.uploader {
  margin-bottom: 14px;
}

.upload-text {
  padding: 10px 0;
}

.upload-title {
  margin: 0 0 4px;
  font-size: 14px;
  color: var(--rag-text);
}

.upload-tip {
  margin: 0;
  font-size: 12px;
  color: var(--rag-text-weak);
}

.progress {
  margin-bottom: 6px;
}

.progress-tip {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--rag-text-weak);
}

.table {
  background: var(--rag-panel);
  border: 1px solid var(--rag-border);
  border-radius: var(--rag-radius);
}

.chunk-list {
  min-height: 200px;
}

.chunk-summary {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--rag-text-weak);
}

.chunk {
  padding: 12px 14px;
  margin-bottom: 10px;
  background: var(--rag-panel);
  border: 1px solid var(--rag-border);
  border-radius: var(--rag-radius);
}

.chunk-head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.chunk-index {
  font-size: 12px;
  font-weight: 700;
  color: var(--rag-primary);
}

.chunk-range {
  font-size: 11px;
  color: var(--rag-text-weak);
}

.chunk-text {
  max-height: 220px;
  margin: 0;
  overflow: auto;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>