import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import ToolsPage from './ToolsPage'
import { toolsApi } from '@/api/tools'

vi.mock('@/api/tools', () => ({
  toolsApi: {
    unlockOutlook: vi.fn().mockResolvedValue({ success: true, data: { task_id: 't1' } }),
    validateKey: vi.fn().mockResolvedValue({ success: true, data: { task_id: 't2' } }),
    activatePlus: vi.fn().mockResolvedValue({ success: true, data: { task_id: 't3' } }),
    orchestrateAllPlatforms: vi.fn().mockResolvedValue({ success: true, data: { task_id: 't4' } }),
    orchestrateFullFlow: vi.fn().mockResolvedValue({ success: true, data: { task_id: 't5' } }),
  },
}))

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ToolsPage smoke', () => {
  it('renders heading and all 5 tool cards', () => {
    renderWithProviders(<ToolsPage />)
    expect(screen.getByText('工具 / 运维')).toBeInTheDocument()
    expect(screen.getByText('解锁 Outlook 账号')).toBeInTheDocument()
    expect(screen.getByText('校验 Session Key')).toBeInTheDocument()
    expect(screen.getByText('激活 ChatGPT Plus')).toBeInTheDocument()
    expect(screen.getByText('多平台批量注册')).toBeInTheDocument()
    expect(screen.getByText('全流程注册')).toBeInTheDocument()
  })

  it('renders an 执行 button per card', () => {
    renderWithProviders(<ToolsPage />)
    expect(screen.getAllByRole('button', { name: /执\s*行/ })).toHaveLength(5)
  })

  it('submits 校验 Session Key form and calls validateKey with the input', async () => {
    renderWithProviders(<ToolsPage />)
    const textarea = screen.getByPlaceholderText('refresh_token / session key')
    fireEvent.change(textarea, { target: { value: 'mykey' } })
    fireEvent.submit(textarea.closest('form') as HTMLFormElement)
    await waitFor(() => {
      expect(toolsApi.validateKey).toHaveBeenCalledWith('mykey')
    })
  })
})
