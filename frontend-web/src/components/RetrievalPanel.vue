<script setup lang="ts">
import { computed, ref } from 'vue'

import { useChatStore } from '@/stores/chat'

/**
 * 检索调参面板。
 * 这里的取值会原样作为 POST /chat/stream 的 retrieval 字段发送，
 * 后端未传的字段才回落到 settings 默认值，因此可以实时对比不同策略的召回效果。
 */
const chat = useChatStore()
const expanded = ref<string[]>(['panel'])

const MODE_LABELS: Record<string, string> = {
  vector: '纯向量',
  bm25: '纯 BM25',
  hybrid: '混合检索',
}

const summary = computed(() => {
  const form = chat.retrieval
  const rerank = form.use_rerank ? '重排开启' : '重排关闭'
  return `${MODE_LABELS[form.mode]} · Top${form.top_k} · ${rerank}`
})

const needVector = computed(() => chat.retrieval.mode !== 'bm25')
const needBm25 = computed(() => chat.retrieval.mode !== 'vector')
</script>

<template>
  <el-collapse v-model="expanded" class="retrieval-panel">
    <el-collapse-item name="panel">
      <template #title>
        <div class="panel-title">
          <span class="label">检索参数</span>
          <el-tag size="small" type="info" effect="plain">{{ summary }}</el-tag>
        </div>
      </template>

      <el-form label-width="96px" label-position="left" size="small" class="panel-form">
        <el-form-item label="检索模式">
          <el-radio-group v-model="chat.retrieval.mode">
            <el-radio-button value="hybrid">混合</el-radio-button>
            <el-radio-button value="vector">向量</el-radio-button>
            <el-radio-button value="bm25">BM25</el-radio-button>
          </el-radio-group>
          <span class="extra">混合模式并行召回后用 RRF 融合，兼顾语义与精确术语</span>
        </el-form-item>

        <el-form-item label="最终条数">
          <el-slider v-model="chat.retrieval.top_k" :min="1" :max="20" :step="1" show-stops />
        </el-form-item>

        <el-form-item label="向量召回数">
          <el-slider
            v-model="chat.retrieval.vector_top_k"
            :min="5"
            :max="50"
            :step="5"
            show-stops
            :disabled="!needVector"
          />
        </el-form-item>

        <el-form-item label="BM25 召回数">
          <el-slider
            v-model="chat.retrieval.bm25_top_k"
            :min="5"
            :max="50"
            :step="5"
            show-stops
            :disabled="!needBm25"
          />
        </el-form-item>

        <el-form-item label="相似度阈值">
          <el-slider
            v-model="chat.retrieval.score_threshold"
            :min="0"
            :max="0.9"
            :step="0.05"
            show-input
            :disabled="!needVector"
          />
        </el-form-item>

        <el-form-item label="重排">
          <el-switch v-model="chat.retrieval.use_rerank" active-text="启用 Cross-Encoder" />
        </el-form-item>

        <el-form-item v-if="chat.retrieval.use_rerank" label="重排候选">
          <el-slider v-model="chat.retrieval.rerank_top_n" :min="1" :max="20" :step="1" show-stops />
        </el-form-item>

        <el-form-item label=" ">
          <el-button size="small" @click="chat.resetRetrieval()">重置为默认</el-button>
          <span class="extra">默认值与后端 .env 中的 retrieval 配置一致</span>
        </el-form-item>
      </el-form>
    </el-collapse-item>
  </el-collapse>
</template>

<style scoped>
.retrieval-panel {
  border-top: 1px solid var(--rag-border);
  border-bottom: none;
}

.panel-title {
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 13px;
}

.panel-title .label {
  font-weight: 600;
  color: #4a5261;
}

.panel-form {
  padding: 4px 4px 0;
}

.extra {
  margin-left: 12px;
  font-size: 11px;
  color: var(--rag-text-weak);
}

:deep(.el-collapse-item__header) {
  height: 40px;
  padding: 0 4px;
  border-bottom: none;
}

:deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

:deep(.el-slider) {
  padding: 0 8px;
}
</style>