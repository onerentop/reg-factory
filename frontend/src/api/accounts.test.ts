import { describe, it, expect, vi, beforeEach } from 'vitest'
import { accountApi } from '@/api/accounts'

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
const mockPut = apiClient.put as ReturnType<typeof vi.fn>
const mockDelete = apiClient.delete as ReturnType<typeof vi.fn>

beforeEach(() => vi.clearAllMocks())

describe('accountApi.list', () => {
  it('calls GET /accounts with params', () => {
    const params = { platform: 'gmail', status: 'active', page: 1, page_size: 20 }
    accountApi.list(params)
    expect(mockGet).toHaveBeenCalledWith('/accounts', { params })
  })

  it('calls GET /accounts with empty params object', () => {
    accountApi.list({})
    expect(mockGet).toHaveBeenCalledWith('/accounts', { params: {} })
  })
})

describe('accountApi.get', () => {
  it('calls GET /accounts/:id', () => {
    accountApi.get('abc-123')
    expect(mockGet).toHaveBeenCalledWith('/accounts/abc-123')
  })
})

describe('accountApi.create', () => {
  it('calls POST /accounts with data', () => {
    const data = { email: 'test@example.com', platform: 'gmail', password: 'secret' }
    accountApi.create(data)
    expect(mockPost).toHaveBeenCalledWith('/accounts', data)
  })

  it('calls POST /accounts without optional password', () => {
    const data = { email: 'test@example.com', platform: 'outlook' }
    accountApi.create(data)
    expect(mockPost).toHaveBeenCalledWith('/accounts', data)
  })
})

describe('accountApi.update', () => {
  it('calls PUT /accounts/:id with partial data', () => {
    const data = { status: 'completed' }
    accountApi.update('xyz-456', data)
    expect(mockPut).toHaveBeenCalledWith('/accounts/xyz-456', data)
  })
})

describe('accountApi.delete', () => {
  it('calls DELETE /accounts/:id', () => {
    accountApi.delete('id-001')
    expect(mockDelete).toHaveBeenCalledWith('/accounts/id-001')
  })
})

describe('accountApi.batchDelete', () => {
  it('calls POST /accounts/batch/delete with account_ids array', () => {
    const ids = ['id-1', 'id-2', 'id-3']
    accountApi.batchDelete(ids)
    expect(mockPost).toHaveBeenCalledWith('/accounts/batch/delete', { account_ids: ids })
  })
})

describe('accountApi.batchExport', () => {
  it('calls POST /accounts/batch/export with full data', () => {
    const data = { account_ids: ['id-1'], format: 'csv', platform: 'gmail', status: 'active' }
    accountApi.batchExport(data)
    expect(mockPost).toHaveBeenCalledWith('/accounts/batch/export', data)
  })

  it('calls POST /accounts/batch/export with only required format', () => {
    const data = { format: 'json' }
    accountApi.batchExport(data)
    expect(mockPost).toHaveBeenCalledWith('/accounts/batch/export', data)
  })
})

describe('accountApi.batchRetry', () => {
  it('calls POST /accounts/batch/retry with account_ids', () => {
    const ids = ['id-10', 'id-20']
    accountApi.batchRetry(ids)
    expect(mockPost).toHaveBeenCalledWith('/accounts/batch/retry', { account_ids: ids })
  })
})

describe('accountApi.getSteps', () => {
  it('calls GET /accounts/:id/steps', () => {
    accountApi.getSteps('step-account-id')
    expect(mockGet).toHaveBeenCalledWith('/accounts/step-account-id/steps')
  })
})

describe('accountApi.importAccounts', () => {
  it('calls POST /accounts/import with platform, format, content', () => {
    const data = { platform: 'gmail', format: 'csv', content: 'email,password\nfoo@bar.com,pass' }
    accountApi.importAccounts(data)
    expect(mockPost).toHaveBeenCalledWith('/accounts/import', data)
  })
})
