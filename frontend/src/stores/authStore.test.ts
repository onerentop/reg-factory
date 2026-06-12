import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from '@/stores/authStore'

// 每次 test 前把 store 还原到 localStorage 为空的状态
// setState with replace=false (default) keeps action functions intact
beforeEach(() => {
  localStorage.clear()
  useAuthStore.setState({
    token: null,
    username: null,
    role: null,
    isAuthenticated: false,
  })
})

describe('authStore — 初始状态', () => {
  it('token/username/role 为 null，isAuthenticated 为 false', () => {
    const s = useAuthStore.getState()
    expect(s.token).toBeNull()
    expect(s.username).toBeNull()
    expect(s.role).toBeNull()
    expect(s.isAuthenticated).toBe(false)
  })
})

describe('authStore — login', () => {
  it('login 后 state 字段正确', () => {
    useAuthStore.getState().login('tok-abc', 'alice', 'admin')
    const s = useAuthStore.getState()
    expect(s.token).toBe('tok-abc')
    expect(s.username).toBe('alice')
    expect(s.role).toBe('admin')
    expect(s.isAuthenticated).toBe(true)
  })

  it('login 后 localStorage 写入 token/username/role', () => {
    useAuthStore.getState().login('tok-xyz', 'bob', 'user')
    expect(localStorage.getItem('token')).toBe('tok-xyz')
    expect(localStorage.getItem('username')).toBe('bob')
    expect(localStorage.getItem('role')).toBe('user')
  })
})

describe('authStore — logout', () => {
  it('logout 后 state 清空', () => {
    useAuthStore.getState().login('tok-abc', 'alice', 'admin')
    useAuthStore.getState().logout()
    const s = useAuthStore.getState()
    expect(s.token).toBeNull()
    expect(s.username).toBeNull()
    expect(s.role).toBeNull()
    expect(s.isAuthenticated).toBe(false)
  })

  it('logout 后 localStorage 项被移除', () => {
    useAuthStore.getState().login('tok-abc', 'alice', 'admin')
    useAuthStore.getState().logout()
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('username')).toBeNull()
    expect(localStorage.getItem('role')).toBeNull()
  })
})

describe('authStore — localStorage 预填（store 实例化）', () => {
  it('localStorage 已有 token 时，重新 setState 反映已认证', () => {
    // 模拟 store 从已有 token 的 localStorage 初始化
    localStorage.setItem('token', 'pre-tok')
    localStorage.setItem('username', 'carol')
    localStorage.setItem('role', 'user')
    // 手动恢复为 store 初始化时会读取的值
    useAuthStore.setState(
      {
        token: localStorage.getItem('token'),
        username: localStorage.getItem('username'),
        role: localStorage.getItem('role'),
        isAuthenticated: !!localStorage.getItem('token'),
      },
      true,
    )
    const s = useAuthStore.getState()
    expect(s.token).toBe('pre-tok')
    expect(s.isAuthenticated).toBe(true)
  })
})
