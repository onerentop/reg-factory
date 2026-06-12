import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import LogsPage from './LogsPage'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ data: { items: [], total: 0 } }),
    }),
  )
})

describe('LogsPage smoke', () => {
  it('renders page heading', async () => {
    renderWithProviders(<LogsPage />)
    await waitFor(() => {
      expect(screen.getByText('日志查询')).toBeInTheDocument()
    })
  })

  it('renders logs table', async () => {
    renderWithProviders(<LogsPage />)
    await waitFor(() => {
      expect(screen.getByRole('table')).toBeInTheDocument()
    })
  })

  it('renders refresh button', async () => {
    renderWithProviders(<LogsPage />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /刷新/ })).toBeInTheDocument()
    })
  })
})
