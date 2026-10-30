/** 鉴权状态：token 持久化在 localStorage，刷新页面后用 /auth/me 补回用户信息 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { fetchCurrentUser, loginAccount, registerAccount } from '@/api/auth'
import { clearToken, getToken, setToken } from '@/api/http'
import type { TokenPayload, User } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(getToken() ?? '')
  const user = ref<User | null>(null)
  const loading = ref(false)

  const isLoggedIn = computed(() => Boolean(token.value))
  const displayName = computed(() => user.value?.username ?? '访客')

  function applyToken(payload: TokenPayload): void {
    token.value = payload.access_token
    user.value = payload.user
    setToken(payload.access_token)
  }

  async function login(username: string, password: string): Promise<void> {
    loading.value = true
    try {
      applyToken(await loginAccount(username, password))
    } finally {
      loading.value = false
    }
  }

  async function register(username: string, password: string): Promise<void> {
    loading.value = true
    try {
      applyToken(await registerAccount(username, password))
    } finally {
      loading.value = false
    }
  }

  /** 刷新页面后恢复用户信息；已有则直接返回，避免重复请求 */
  async function ensureProfile(): Promise<User | null> {
    if (!token.value) {
      return null
    }
    if (user.value) {
      return user.value
    }
    user.value = await fetchCurrentUser()
    return user.value
  }

  function logout(): void {
    token.value = ''
    user.value = null
    clearToken()
  }

  return {
    token,
    user,
    loading,
    isLoggedIn,
    displayName,
    login,
    register,
    ensureProfile,
    logout,
  }
})