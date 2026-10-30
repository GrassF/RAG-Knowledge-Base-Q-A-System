<script setup lang="ts">
import { computed } from 'vue'

import type { SourceItem } from '@/types'

const props = defineProps<{ source: SourceItem }>()
const emit = defineEmits<{ open: [source: SourceItem] }>()

/** 优先展示重排分，没有重排时退回 RRF 融合分 */
const scoreLabel = computed(() => {
  const { rerank_score: rerank, rrf_score: rrf, vector_score: vector, bm25_score: bm25 } = props.source
  if (rerank !== null && rerank !== undefined) {
    return `重排 ${rerank.toFixed(3)}`
  }
  if (rrf !== null && rrf !== undefined) {
    return `融合 ${rrf.toFixed(4)}`
  }
  if (vector !== null && vector !== undefined) {
    return `向量 ${vector.toFixed(3)}`
  }
  if (bm25 !== null && bm25 !== undefined) {
    return `BM25 ${bm25.toFixed(2)}`
  }
  return '未打分'
})
</script>

<template>
  <button type="button" class="source-card" @click="emit('open', source)">
    <div class="head">
      <span class="index">[{{ source.index }}]</span>
      <span class="filename" :title="source.filename">{{ source.filename }}</span>
      <span class="score">{{ scoreLabel }}</span>
    </div>

    <div class="location">
      <el-tag v-if="source.page" size="small" type="info" effect="plain">
        第 {{ source.page }} 页
      </el-tag>
      <el-tag v-if="source.section" size="small" type="info" effect="plain">
        {{ source.section }}
      </el-tag>
      <span v-if="!source.page && !source.section" class="no-location">无页码/章节信息</span>
    </div>

    <p class="snippet">{{ source.snippet }}</p>
  </button>
</template>

<style scoped>
.source-card {
  display: block;
  width: 100%;
  padding: 10px 12px;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  background: var(--rag-panel);
  border: 1px solid var(--rag-border);
  border-radius: var(--rag-radius);
  transition: all 0.15s ease;
}

.source-card:hover {
  border-color: #b9caff;
  box-shadow: 0 4px 14px rgb(58 111 247 / 10%);
}

.head {
  display: flex;
  gap: 8px;
  align-items: center;
}

.index {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 700;
  color: var(--rag-primary);
}

.filename {
  flex: 1;
  overflow: hidden;
  font-size: 13px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.score {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--rag-text-weak);
}

.location {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-top: 6px;
}

.no-location {
  font-size: 11px;
  color: var(--rag-text-weak);
}

.snippet {
  display: -webkit-box;
  margin: 8px 0 0;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.6;
  color: #5b6472;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
</style>