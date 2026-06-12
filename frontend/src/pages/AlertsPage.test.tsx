import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import AlertsPage from './AlertsPage'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ data: [] }),
    }),
  )
})

describe('AlertsPage smoke', () => {
  it('renders page heading', async () => {
    renderWithProviders(<AlertsPage />)
    await waitFor(() => {
      expect(screen.getByText(/告警通知/)).toBeInTheDocument()
    })
  })

  it('renders rules tab and add-rule button', async () => {
    renderWithProviders(<AlertsPage />)
    await waitFor(() => {
      expect(screen.getByText('告警规则')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: /添加规则/ })).toBeInTheDocument()
  })
})
