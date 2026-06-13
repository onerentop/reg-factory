import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import SmsConfigPage from './SmsConfigPage'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (url.includes('/prices')) return Promise.resolve({ json: () => Promise.resolve({ data: [{ country: '52', cost: 0.1, count: 100 }] }) })
    if (url.includes('/config/gmail_sms_config')) return Promise.resolve({ json: () => Promise.resolve({ data: { value: { provider: 'hero_sms', country: '52', max_price: '0.2', fixed_price: false } } }) })
    if (url.includes('/providers')) return Promise.resolve({ json: () => Promise.resolve({ data: [{ name: 'hero_sms', display_name: 'HeroSMS' }] }) })
    if (url.includes('/sms/config')) return Promise.resolve({ json: () => Promise.resolve({ data: [] }) })
    return Promise.resolve({ json: () => Promise.resolve({ data: [] }) })
  }))
})

describe('SmsConfigPage Google 接码块', () => {
  it('渲染 Google 注册接码标题', async () => {
    renderWithProviders(<SmsConfigPage />)
    await waitFor(() => expect(screen.getByText(/Google 注册接码/)).toBeInTheDocument())
  })
})
