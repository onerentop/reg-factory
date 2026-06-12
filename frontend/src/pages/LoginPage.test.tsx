import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import LoginPage from './LoginPage'

describe('LoginPage smoke', () => {
  it('renders without crashing and shows login form', () => {
    renderWithProviders(<LoginPage />)
    expect(screen.getByText('RegFactory')).toBeInTheDocument()
    // antd Button renders text with a span, accessible name may have spaces; use regex
    expect(screen.getByRole('button', { name: /登/ })).toBeInTheDocument()
  })
})
