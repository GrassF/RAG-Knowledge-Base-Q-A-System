/** 鉴权接口：注册 / 登录 / 当前用户 */
import { request } from './http'
import type { TokenPayload, User } from '@/types'

export function registerAccount(username: string, password: string): Promise<TokenPayload> {
  return request<TokenPayload>({
    url: '/auth/register',
    method: 'post',
    data: { username, password },
  })
}

export function loginAccount(username: string, password: string): Promise<TokenPayload> {
  return request<TokenPayload>({
    url: '/auth/login',
    method: 'post',
    data: { username, password },
  })
}

export function fetchCurrentUser(): Promise<User> {
  return request<User>({ url: '/auth/me', method: 'get' })
}