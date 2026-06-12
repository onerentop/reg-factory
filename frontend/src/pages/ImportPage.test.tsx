import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import ImportPage from './ImportPage'

describe('ImportPage smoke', () => {
  it('renders page heading', () => {
    renderWithProviders(<ImportPage />)
    expect(screen.getByText(/数据导入/)).toBeInTheDocument()
  })

  it('renders confirm-import button (disabled until file chosen)', () => {
    renderWithProviders(<ImportPage />)
    expect(screen.getByRole('button', { name: /确认导入/ })).toBeInTheDocument()
  })
})
