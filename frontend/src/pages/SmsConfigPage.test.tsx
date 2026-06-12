import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import SmsConfigPage from './SmsConfigPage'

beforeEach(() => {
  // Two fetches in Promise.all: /api/sms/providers and /api/sms/config
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (url.includes('providers')) {
        return Promise.resolve({ json: () => Promise.resolve({ data: [] }) })
      }
      // /api/sms/config
      return Promise.resolve({ json: () => Promise.resolve({ data: [] }) })
    }),
  )
})

describe('SmsConfigPage smoke', () => {
  it('renders page heading after loading', async () => {
    renderWithProviders(<SmsConfigPage />)
    await waitFor(() => {
      expect(screen.getByText('接码平台配置')).toBeInTheDocument()
    })
  })

  it('renders providers table', async () => {
    renderWithProviders(<SmsConfigPage />)
    await waitFor(() => {
      expect(screen.getByRole('table')).toBeInTheDocument()
    })
  })
})
