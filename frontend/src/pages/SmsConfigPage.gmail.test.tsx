import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import SmsConfigPage from './SmsConfigPage'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (url.includes('/offers')) return Promise.resolve({ json: () => Promise.resolve({ data: { prices: { min: 0.1 }, counts: { total: 100, physical: 50 }, tiers: [{ price: 0.1, count: 50 }, { price: 0.2, count: 80 }] } }) })
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

  it('复访已存配置后展示价位档', async () => {
    renderWithProviders(<SmsConfigPage />)
    // gmail_sms_config 已存 country=52 → loadOffers → 展示 hero 价位阶梯
    await waitFor(() => expect(screen.getByText(/\$0\.1 \/ 50个/)).toBeInTheDocument())
    expect(screen.getByText(/\$0\.2 \/ 80个/)).toBeInTheDocument()
  })
})
