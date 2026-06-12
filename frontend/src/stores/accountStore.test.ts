import { describe, it, expect, beforeEach } from 'vitest'
import { useAccountStore } from '@/stores/accountStore'
import type { Account } from '@/api/accounts'

// accountStore 不直接调用 API，只保存外部传入的数据，无需 mock

const makeAccount = (id: string): Account => ({
  id,
  email: `${id}@test.com`,
  platform: 'gmail',
  status: 'pending',
  current_step: 0,
  total_steps: 5,
  steps: [],
})

// setState with replace=true would drop action functions; use partial reset instead
function resetStore() {
  useAccountStore.setState({
    accounts: [],
    total: 0,
    loading: false,
    currentPage: 1,
    pageSize: 20,
    selectedIds: [],
    expandedRowId: null,
  })
}

beforeEach(() => {
  resetStore()
})

describe('accountStore — 初始状态', () => {
  it('默认值正确', () => {
    const s = useAccountStore.getState()
    expect(s.accounts).toEqual([])
    expect(s.total).toBe(0)
    expect(s.loading).toBe(false)
    expect(s.currentPage).toBe(1)
    expect(s.pageSize).toBe(20)
    expect(s.selectedIds).toEqual([])
    expect(s.expandedRowId).toBeNull()
  })
})

describe('accountStore — setAccounts', () => {
  it('设置 accounts 列表和 total', () => {
    const list = [makeAccount('a1'), makeAccount('a2')]
    useAccountStore.getState().setAccounts(list, 42)
    const s = useAccountStore.getState()
    expect(s.accounts).toHaveLength(2)
    expect(s.total).toBe(42)
    expect(s.accounts[0].id).toBe('a1')
  })
})

describe('accountStore — setLoading', () => {
  it('setLoading(true/false)', () => {
    useAccountStore.getState().setLoading(true)
    expect(useAccountStore.getState().loading).toBe(true)
    useAccountStore.getState().setLoading(false)
    expect(useAccountStore.getState().loading).toBe(false)
  })
})

describe('accountStore — 分页', () => {
  it('setPage 更新 currentPage', () => {
    useAccountStore.getState().setPage(3)
    expect(useAccountStore.getState().currentPage).toBe(3)
  })

  it('setPageSize 更新 pageSize 并重置 currentPage 为 1', () => {
    useAccountStore.getState().setPage(5)
    useAccountStore.getState().setPageSize(50)
    const s = useAccountStore.getState()
    expect(s.pageSize).toBe(50)
    expect(s.currentPage).toBe(1)
  })
})

describe('accountStore — 选择行', () => {
  it('toggleSelect 选中未选中的 id', () => {
    useAccountStore.getState().toggleSelect('id-1')
    expect(useAccountStore.getState().selectedIds).toContain('id-1')
  })

  it('toggleSelect 再次调用取消选中', () => {
    useAccountStore.getState().toggleSelect('id-1')
    useAccountStore.getState().toggleSelect('id-1')
    expect(useAccountStore.getState().selectedIds).not.toContain('id-1')
  })

  it('selectAll 覆盖 selectedIds', () => {
    useAccountStore.getState().toggleSelect('id-1')
    useAccountStore.getState().selectAll(['id-2', 'id-3'])
    expect(useAccountStore.getState().selectedIds).toEqual(['id-2', 'id-3'])
  })

  it('clearSelection 清空 selectedIds', () => {
    useAccountStore.getState().selectAll(['id-1', 'id-2'])
    useAccountStore.getState().clearSelection()
    expect(useAccountStore.getState().selectedIds).toEqual([])
  })
})

describe('accountStore — expandedRowId', () => {
  it('setExpandedRow 设置展开行 id', () => {
    useAccountStore.getState().setExpandedRow('row-5')
    expect(useAccountStore.getState().expandedRowId).toBe('row-5')
  })

  it('setExpandedRow(null) 清空', () => {
    useAccountStore.getState().setExpandedRow('row-5')
    useAccountStore.getState().setExpandedRow(null)
    expect(useAccountStore.getState().expandedRowId).toBeNull()
  })
})
