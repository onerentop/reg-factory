import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authApi } from '@/api/auth'

vi.mock('@/api/client', () => ({
  default: { post: vi.fn() },
}))

import apiClient from '@/api/client'

const mockPost = apiClient.post as ReturnType<typeof vi.fn>

beforeEach(() => vi.clearAllMocks())

describe('authApi.login', () => {
  it('calls POST /auth/login with username and password', () => {
    authApi.login('admin', 'secret123')
    expect(mockPost).toHaveBeenCalledWith('/auth/login', {
      username: 'admin',
      password: 'secret123',
    })
  })
})
