import { describe, it, expect, vi, beforeEach } from 'vitest'
import { dashboardApi } from '@/api/dashboard'

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

beforeEach(() => vi.clearAllMocks())

describe('dashboardApi.getData', () => {
  it('calls GET /dashboard', () => {
    dashboardApi.getData()
    expect(mockGet).toHaveBeenCalledWith('/dashboard')
  })

  it('calls GET /dashboard with no extra arguments', () => {
    dashboardApi.getData()
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(mockGet.mock.calls[0]).toEqual(['/dashboard'])
  })
})
