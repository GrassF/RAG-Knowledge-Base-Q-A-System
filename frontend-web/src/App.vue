<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { AUTH_EXPIRED_EVENT } from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

/** 登录页不显示顶栏与侧边结构 */
const showChrome = computed(() => route.name !== 'login')

function handleAuthExpired(): void {
  auth.logout()
  ElMessage.warning('登录状态已失效，请重新登录')
}

function handleLogout(): void {
  auth.logout()
  ElMessage.success('已退出登录')
  void router.replace({ name: 'login' })
}

onMounted(() => {
  window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired)
  // 刷新页面后 token 还在，但用户信息需要重新拉一次
  if (auth.isLoggedIn && !auth.user) {
    void auth.ensureProfile().catch(() => undefined)
  }
})

onUnmounted(() => {
  window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired)
})
</script>

<template>
  <div class="app-shell">
    <header v-if="showChrome" class="app-header">
      <div class="brand">
        <span class="logo">RAG</span>
        <span class="brand-text">知识库智能问答</span>
      </div>

      <nav class="nav">
        <router-link to="/chat" class="nav-item" active-class="active">智能问答</router-link>
        <router-link to="/documents" class="nav-item" active-class="active">知识库</router-link>
      </nav>

      <div class="account">
        <el-dropdown trigger="click" @command="handleLogout">
          <span class="account-name">{{ auth.displayName }}</span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <main class="app-body">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.app-header {
  display: flex;
  flex-shrink: 0;
  gap: 32px;
  align-items: center;
  height: 56px;
  padding: 0 20px;
  background: var(--rag-panel);
  border-bottom: 1px solid var(--rag-border);
}

.brand {
  display: flex;
  gap: 10px;
  align-items: center;
}

.logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.5px;
  background: linear-gradient(135deg, #3a6ff7, #6a9cff);
  border-radius: 9px;
}

.brand-text {
  font-size: 15px;
  font-weight: 600;
}

.nav {
  display: flex;
  gap: 6px;
}

.nav-item {
  padding: 6px 14px;
  font-size: 14px;
  color: var(--rag-text-weak);
  border-radius: 8px;
  transition: all 0.15s ease;
}

.nav-item:hover {
  color: var(--rag-text);
  background: #f2f4f9;
}

.nav-item.active {
  color: var(--rag-primary);
  background: #eef3ff;
}

.account {
  margin-left: auto;
}

.account-name {
  font-size: 14px;
  color: var(--rag-text);
  cursor: pointer;
  outline: none;
}

.app-body {
  flex: 1;
  min-height: 0;
}
</style>