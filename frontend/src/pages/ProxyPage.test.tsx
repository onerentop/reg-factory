import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
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

function stubFetch(rows: any[]) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ data: rows }),
  }))
}

describe('绑定展示', () => {
  it('渲染今日与累计绑定列', async () => {
    stubFetch([{ id: 'p1', type: 'http', host: '1.2.3.4', port: 8080, status: 'active',
                 today_bound: 1, total_bound: 7,
                 today_profile_name: 'a@gmail.com', available_today: false }])
    renderWithProviders(<ProxyPage />)
    await waitFor(() => expect(screen.getByText('今日 1/1')).toBeInTheDocument())
    expect(screen.getByText('累计 7')).toBeInTheDocument()
  })

  it('未绑定过的代理显示今日 0/1', async () => {
    stubFetch([{ id: 'p1', type: 'http', host: '1.2.3.4', port: 8080, status: 'active',
                 today_bound: 0, total_bound: 0,
                 today_profile_name: null, available_today: true }])
    renderWithProviders(<ProxyPage />)
    await waitFor(() => expect(screen.getByText('今日 0/1')).toBeInTheDocument())
  })

  it('后端未返回绑定字段时不崩溃', async () => {
    stubFetch([{ id: 'p1', type: 'http', host: '1.2.3.4', port: 8080, status: 'active' }])
    renderWithProviders(<ProxyPage />)
    await waitFor(() => expect(screen.getByText('今日 0/1')).toBeInTheDocument())
    expect(screen.getByText('累计 0')).toBeInTheDocument()
  })
})

describe('批量导入', () => {
  it('渲染批量导入按钮', async () => {
    stubFetch([])
    renderWithProviders(<ProxyPage />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /批量导入/ })).toBeInTheDocument()
    })
  })

  it('提交后调用导入接口', async () => {
    stubFetch([])
    renderWithProviders(<ProxyPage />)
    fireEvent.click(await screen.findByRole('button', { name: /批量导入/ }))
    fireEvent.change(screen.getByPlaceholderText(/每行一条/), {
      target: { value: '1.2.3.4:8080:u:p' },
    })
    fireEvent.click(screen.getByRole('button', { name: /确\s*定/ }))
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        '/api/proxy/import',
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })
})
