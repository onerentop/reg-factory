import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import AuditPage from './AuditPage'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ data: { items: [], total: 0 } }),
    }),
  )
})

describe('AuditPage smoke', () => {
  it('renders page heading', async () => {
    renderWithProviders(<AuditPage />)
    await waitFor(() => {
      expect(screen.getByText('操作审计')).toBeInTheDocument()
    })
  })

  it('renders audit table', async () => {
    renderWithProviders(<AuditPage />)
    await waitFor(() => {
      expect(screen.getByRole('table')).toBeInTheDocument()
    })
  })
})
