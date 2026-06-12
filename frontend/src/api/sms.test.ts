import { describe, it, expect, vi, beforeEach } from 'vitest'
import { smsApi } from '@/api/sms'

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
const mockPut = apiClient.put as ReturnType<typeof vi.fn>

beforeEach(() => vi.clearAllMocks())

describe('smsApi.listProviders', () => {
  it('calls GET /sms/providers', () => {
    smsApi.listProviders()
    expect(mockGet).toHaveBeenCalledWith('/sms/providers')
  })
})

describe('smsApi.getBalance', () => {
  it('calls GET /sms/providers/:name/balance', () => {
    smsApi.getBalance('twilio')
    expect(mockGet).toHaveBeenCalledWith('/sms/providers/twilio/balance')
  })

  it('encodes provider name in URL', () => {
    smsApi.getBalance('sms-activate')
    expect(mockGet).toHaveBeenCalledWith('/sms/providers/sms-activate/balance')
  })
})

describe('smsApi.getConfigs', () => {
  it('calls GET /sms/config', () => {
    smsApi.getConfigs()
    expect(mockGet).toHaveBeenCalledWith('/sms/config')
  })
})

describe('smsApi.saveConfig', () => {
  it('calls PUT /sms/config/:providerName with data', () => {
    const data = { enabled: 'true', priority: 1, config: { api_key: 'abc' } }
    smsApi.saveConfig('twilio', data)
    expect(mockPut).toHaveBeenCalledWith('/sms/config/twilio', data)
  })

  it('calls PUT /sms/config/:providerName with partial data', () => {
    smsApi.saveConfig('vonage', { priority: 2 })
    expect(mockPut).toHaveBeenCalledWith('/sms/config/vonage', { priority: 2 })
  })
})
