import { create } from 'zustand'
import type { Account } from '../api/accounts'

interface AccountState {
  accounts: Account[]
  total: number
  loading: boolean
  currentPage: number
  pageSize: number
  selectedIds: string[]
  expandedRowId: string | null
  setAccounts: (accounts: Account[], total: number) => void
  setLoading: (loading: boolean) => void
  setPage: (page: number) => void
  setPageSize: (size: number) => void
  toggleSelect: (id: string) => void
  selectAll: (ids: string[]) => void
  clearSelection: () => void
  setExpandedRow: (id: string | null) => void
}

export const useAccountStore = create<AccountState>((set) => ({
  accounts: [],
  total: 0,
  loading: false,
  currentPage: 1,
  pageSize: 20,
  selectedIds: [],
  expandedRowId: null,
  setAccounts: (accounts, total) => set({ accounts, total }),
  setLoading: (loading) => set({ loading }),
  setPage: (page) => set({ currentPage: page }),
  setPageSize: (size) => set({ pageSize: size, currentPage: 1 }),
  toggleSelect: (id) =>
    set((state) => ({
      selectedIds: state.selectedIds.includes(id)
        ? state.selectedIds.filter((i) => i !== id)
        : [...state.selectedIds, id],
    })),
  selectAll: (ids) => set({ selectedIds: ids }),
  clearSelection: () => set({ selectedIds: [] }),
  setExpandedRow: (id) => set({ expandedRowId: id }),
}))
