import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import ProxyPage from './ProxyPage'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ data: [] }),
    }),
  )
})

describe('ProxyPage smoke', () => {
  it('renders page heading', async () => {
    renderWithProviders(<ProxyPage />)
    await waitFor(() => {
      expect(screen.getByText('代理配置')).toBeInTheDocument()
    })
  })

  it('renders add-proxy button', async () => {
    renderWithProviders(<ProxyPage />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /添加代理/ })).toBeInTheDocument()
    })
  })

  it('renders proxy table', async () => {
    renderWithProviders(<ProxyPage />)
    await waitFor(() => {
      expect(screen.getByRole('table')).toBeInTheDocument()
    })
  })
})
