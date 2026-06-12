import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import AccountsPage from './AccountsPage'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      json: () =>
        Promise.resolve({
          data: { items: [], total: 0 },
        }),
    }),
  )
})

describe('AccountsPage smoke', () => {
  it('renders page heading', async () => {
    renderWithProviders(<AccountsPage />)
    // platform param is undefined in MemoryRouter → "Google 账户管理"
    await waitFor(() => {
      expect(
        screen.getByText(/账户管理/),
      ).toBeInTheDocument()
    })
  })

  it('renders the accounts table', async () => {
    renderWithProviders(<AccountsPage />)
    await waitFor(() => {
      expect(screen.getByRole('table')).toBeInTheDocument()
    })
  })

  it('renders new-register button', async () => {
    renderWithProviders(<AccountsPage />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /新建注册/ })).toBeInTheDocument()
    })
  })
})
