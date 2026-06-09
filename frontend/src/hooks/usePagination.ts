import { useState, useCallback } from 'react'

interface PaginationState {
  page: number
  pageSize: number
  total: number
}

export function usePagination(defaultPageSize: number = 20) {
  const [state, setState] = useState<PaginationState>({
    page: 1,
    pageSize: defaultPageSize,
    total: 0,
  })

  const setPage = useCallback((page: number) => {
    setState((prev) => ({ ...prev, page }))
  }, [])

  const setPageSize = useCallback((pageSize: number) => {
    setState((prev) => ({ ...prev, pageSize, page: 1 }))
  }, [])

  const setTotal = useCallback((total: number) => {
    setState((prev) => ({ ...prev, total }))
  }, [])

  return {
    ...state,
    setPage,
    setPageSize,
    setTotal,
    offset: (state.page - 1) * state.pageSize,
  }
}
