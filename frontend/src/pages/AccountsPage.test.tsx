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

/** 按 URL 分派响应：账号列表与代理列表结构不同。 */
function stubFetchByUrl(proxies: any[], registerResult?: any) {
  vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string, init?: any) => {
    if (typeof url === 'string' && url.startsWith('/api/proxy')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: proxies }) })
    }
    if (init?.method === 'POST' && typeof url === 'string' && url.includes('/register/')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(registerResult) })
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ data: { items: [], total: 0 } }),
    })
  }))
}

describe('代理选择约束', () => {
  it('今日已用的代理在下拉中标记为已用', async () => {
    stubFetchByUrl([{ id: 'p1', host: '1.2.3.4', port: 8080, type: 'http',
                      status: 'active', today_bound: 1, available_today: false }])
    renderAccountsPage()
    fireEvent.click(await screen.findByRole('button', { name: /新建注册/ }))
    fireEvent.mouseDown(await screen.findByText(/自动选择/))
    let usedOption: HTMLElement
    await waitFor(() => {
      usedOption = screen.getByText(/1\.2\.3\.4:8080.*今日已用/)
      expect(usedOption).toBeInTheDocument()
    })
    const optionEl = usedOption!.closest('.ant-select-item-option')
    expect(optionEl).toHaveClass('ant-select-item-option-disabled')
  })

  it('今日可用的代理不带已用标记', async () => {
    stubFetchByUrl([{ id: 'p1', host: '1.2.3.4', port: 8080, type: 'http',
                      status: 'active', today_bound: 0, available_today: true }])
    renderAccountsPage()
    fireEvent.click(await screen.findByRole('button', { name: /新建注册/ }))
    fireEvent.mouseDown(await screen.findByText(/自动选择/))
    await waitFor(() => {
      expect(screen.getByText(/1\.2\.3\.4:8080/)).toBeInTheDocument()
    })
    expect(screen.queryByText(/今日已用/)).not.toBeInTheDocument()
  })
})
