/**
 * axios 实例与统一响应拆包。
 *
 * 后端所有接口都返回 { code, message, data, request_id }，
 * 这里把 data 拆出来直接交给调用方，业务代码不用每处都判断 code。
 */
import axios, { type AxiosRequestConfig } from 'axios'

import type { ApiResponse } from '@/types'

/** 后端 API 前缀：开发期由 vite 代理到 127.0.0.1:8000 */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export class ApiError extends Error {
  readonly code: number

  constructor(code: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

// ===================== axios 实例 =====================

export const http = axios.create({
  baseURL: API_BASE_URL,
  // 上传解析与问答（含重排）都可能较慢，给足超时
  timeout: 120_000,
})

/** 发起请求并拆掉外层 { code, message, data } 包装 */
export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const response = await http.request<ApiResponse<T>>(config)
  const payload = response.data

  if (!payload || typeof payload !== 'object' || !('code' in payload)) {
    // 理论上不会发生；兼容直接返回裸数据的场景
    return payload as unknown as T
  }
  if (payload.code !== 0) {
    throw new ApiError(payload.code, payload.message || '请求失败')
  }
  return payload.data as T
}

/** 把任意异常转成可以直接丢给 ElMessage 的文案 */
export function extractErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as ApiResponse<unknown> | undefined
    if (body?.message) {
      return body.message
    }
    if (error.code === 'ECONNABORTED') {
      return '请求超时，请稍后重试'
    }
    if (!error.response) {
      return '无法连接后端服务，请确认已启动 uvicorn'
    }
    return error.message || `请求失败（HTTP ${error.response.status}）`
  }
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}
