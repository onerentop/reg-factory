import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import DashboardPage from './DashboardPage'

// Mock WebSocketClient so connect() doesn't throw in jsdom
vi.mock('../websocket/WebSocketClient', () => ({
  wsClient: {
    connect: vi.fn(),
    on: vi.fn(() => vi.fn()),
    disconnect: vi.fn(),
  },
}))

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      json: () =>
        Promise.resolve({
          data: {
            accounts: { total: 5, success: 3, failed: 1, running: 1 },
            sms: { providers_count: 2, total_balance: 9.99 },
          },
        }),
    }),
  )
})

describe('DashboardPage smoke', () => {
  it('renders heading after data loads', async () => {
    renderWithProviders(<DashboardPage />)
    // Page shows a Spin while loading=true; after fetch resolves it renders h2
    await waitFor(() => {
      expect(screen.getByText('仪表盘')).toBeInTheDocument()
    })
  })

  it('renders activity table section', async () => {
    renderWithProviders(<DashboardPage />)
    await waitFor(() => {
      expect(screen.getByText('最近注册活动')).toBeInTheDocument()
    })
  })
})
