import { describe, it, expect, vi, beforeEach } from 'vitest'
import { authApi } from '@/api/auth'

vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import apiClient from '@/api/client'

const mockGet = apiClient.get as ReturnType<typeof vi.fn>
const mockPost = apiClient.post as ReturnType<typeof vi.fn>
const mockDelete = apiClient.delete as ReturnType<typeof vi.fn>

beforeEach(() => vi.clearAllMocks())

describe('authApi.login', () => {
  it('calls POST /auth/login with username and password', () => {
    authApi.login('admin', 'secret123')
    expect(mockPost).toHaveBeenCalledWith('/auth/login', { username: 'admin', password: 'secret123' })
  })
})

describe('authApi.listUsers', () => {
  it('calls GET /auth/users', () => {
    authApi.listUsers()
    expect(mockGet).toHaveBeenCalledWith('/auth/users')
  })
})

describe('authApi.createUser', () => {
  it('calls POST /auth/users with user data', () => {
    const data = { username: 'newuser', password: 'pass', role: 'viewer' }
    authApi.createUser(data)
    expect(mockPost).toHaveBeenCalledWith('/auth/users', data)
  })
})

describe('authApi.listApiKeys', () => {
  it('calls GET /auth/api-keys with default owner_id=system when no arg', () => {
    authApi.listApiKeys()
    expect(mockGet).toHaveBeenCalledWith('/auth/api-keys', { params: { owner_id: 'system' } })
  })

  it('calls GET /auth/api-keys with provided ownerId', () => {
    authApi.listApiKeys('user-42')
    expect(mockGet).toHaveBeenCalledWith('/auth/api-keys', { params: { owner_id: 'user-42' } })
  })

  it('falls back to system when ownerId is empty string', () => {
    // empty string is falsy, so the || 'system' branch fires
    authApi.listApiKeys('')
    expect(mockGet).toHaveBeenCalledWith('/auth/api-keys', { params: { owner_id: 'system' } })
  })
})

describe('authApi.createApiKey', () => {
  it('calls POST /auth/api-keys with name and scopes', () => {
    const data = { name: 'my-key', scopes: ['read', 'write'] }
    authApi.createApiKey(data)
    expect(mockPost).toHaveBeenCalledWith('/auth/api-keys', data)
  })
})

describe('authApi.revokeApiKey', () => {
  it('calls DELETE /auth/api-keys/:keyId', () => {
    authApi.revokeApiKey('key-999')
    expect(mockDelete).toHaveBeenCalledWith('/auth/api-keys/key-999')
  })
})
