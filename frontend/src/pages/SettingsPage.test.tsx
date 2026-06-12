import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import SettingsPage from './SettingsPage'

beforeEach(() => {
  // UsersTab fetches /api/auth/users; ApiKeysTab fetches /api/auth/api-keys
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ data: [] }),
    }),
  )
})

describe('SettingsPage smoke', () => {
  it('renders page heading', () => {
    renderWithProviders(<SettingsPage />)
    expect(screen.getByText('设置')).toBeInTheDocument()
  })

  it('renders tabs', () => {
    renderWithProviders(<SettingsPage />)
    // Use getAllByText since '并发控制' also appears as a Card title in the active tab panel
    expect(screen.getAllByText('并发控制').length).toBeGreaterThan(0)
    expect(screen.getByRole('tab', { name: '主题' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '用户管理' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'API Key' })).toBeInTheDocument()
  })

  it('renders concurrency tab content (default active tab)', async () => {
    renderWithProviders(<SettingsPage />)
    await waitFor(() => {
      expect(screen.getByText('总并发任务数')).toBeInTheDocument()
    })
  })
})
