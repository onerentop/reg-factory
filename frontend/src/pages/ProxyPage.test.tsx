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

describe('绑定/配额 UI 移除', () => {
  it('不再渲染绑定/配额列', async () => {
    stubFetch([{ id: 'p1', type: 'http', host: '1.2.3.4', port: 8080, status: 'active' }])
    renderWithProviders(<ProxyPage />)
    await waitFor(() => {
      expect(screen.getByText('1.2.3.4')).toBeInTheDocument()
    })
    expect(screen.queryByText(/今日 \/ 累计/)).toBeNull()
    expect(screen.queryByText(/今日可用/)).toBeNull()
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
