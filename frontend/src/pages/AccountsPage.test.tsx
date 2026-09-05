import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ThemeProvider } from '@/theme/ThemeProvider'
import AccountsPage from './AccountsPage'

function renderAccountsPage() {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={['/accounts/outlook']}>
        <Routes>
          <Route path="/accounts/:platform" element={<AccountsPage />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  )
}

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
    renderAccountsPage()
    // platform param is undefined in MemoryRouter → "Google 账户管理"
    await waitFor(() => {
      expect(
        screen.getByText(/账户管理/),
      ).toBeInTheDocument()
    })
  })

  it('renders the accounts table', async () => {
    renderAccountsPage()
    await waitFor(() => {
      expect(screen.getByRole('table')).toBeInTheDocument()
    })
  })

  it('renders new-register button', async () => {
    renderAccountsPage()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /新建注册/ })).toBeInTheDocument()
    })
  })
})

describe('手动选代理不再锁定数量', () => {
  it('选中代理后仍可将数量调至大于 1 并一并提交', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: any) => {
      if (typeof url === 'string' && url.startsWith('/api/proxy')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: [{ id: 'p1', host: '1.2.3.4', port: 8080, type: 'http',
                                                   status: 'active' }] }),
        })
      }
      if (init?.method === 'POST' && typeof url === 'string' && url.includes('/register/')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { task_ids: [] } }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { items: [], total: 0 } }) })
    })
    vi.stubGlobal('fetch', fetchMock)

    renderAccountsPage()
    fireEvent.click(await screen.findByRole('button', { name: /新建注册/ }))

    const countInput = screen.getByRole('spinbutton')
    fireEvent.change(countInput, { target: { value: '5' } })
    expect(countInput).toHaveValue('5')

    fireEvent.mouseDown(await screen.findByText(/自动选择/))
    fireEvent.click(await screen.findByText(/1\.2\.3\.4:8080/))

    expect(countInput).not.toBeDisabled()
    expect(countInput).toHaveValue('5')

    fireEvent.click(screen.getByRole('button', { name: /开始注册/ }))

    await waitFor(() => {
      const registerCall = fetchMock.mock.calls.find(
        (call: any[]) => typeof call[0] === 'string' && call[0].includes('/register/') && call[1]?.method === 'POST',
      )
      expect(registerCall).toBeTruthy()
      const body = JSON.parse(registerCall![1].body)
      expect(body.proxy_id).toBe('p1')
      expect(body.count).toBe(5)
    })
  })
})
