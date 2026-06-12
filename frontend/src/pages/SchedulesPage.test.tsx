import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import SchedulesPage from './SchedulesPage'

describe('SchedulesPage smoke', () => {
  it('renders page heading', () => {
    renderWithProviders(<SchedulesPage />)
    expect(screen.getByText(/定时任务/)).toBeInTheDocument()
  })

  it('renders task table with preset tasks', () => {
    renderWithProviders(<SchedulesPage />)
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('代理健康检查')).toBeInTheDocument()
  })

  it('renders add-task button', () => {
    renderWithProviders(<SchedulesPage />)
    expect(screen.getByRole('button', { name: /添加任务/ })).toBeInTheDocument()
  })
})
