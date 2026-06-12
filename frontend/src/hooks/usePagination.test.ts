import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { usePagination } from '@/hooks/usePagination'

describe('usePagination — 初始值', () => {
  it('使用默认 pageSize=20', () => {
    const { result } = renderHook(() => usePagination())
    expect(result.current.page).toBe(1)
    expect(result.current.pageSize).toBe(20)
    expect(result.current.total).toBe(0)
    expect(result.current.offset).toBe(0)
  })

  it('可自定义 defaultPageSize', () => {
    const { result } = renderHook(() => usePagination(50))
    expect(result.current.pageSize).toBe(50)
  })
})

describe('usePagination — setPage', () => {
  it('setPage 更新 page 和 offset', () => {
    const { result } = renderHook(() => usePagination(10))
    act(() => {
      result.current.setPage(3)
    })
    expect(result.current.page).toBe(3)
    expect(result.current.offset).toBe(20) // (3-1)*10
  })
})

describe('usePagination — setPageSize', () => {
  it('setPageSize 更新 pageSize 并重置 page 为 1', () => {
    const { result } = renderHook(() => usePagination(20))
    act(() => {
      result.current.setPage(4)
    })
    act(() => {
      result.current.setPageSize(50)
    })
    expect(result.current.pageSize).toBe(50)
    expect(result.current.page).toBe(1)
  })
})

describe('usePagination — setTotal', () => {
  it('setTotal 更新 total 不影响 page', () => {
    const { result } = renderHook(() => usePagination())
    act(() => {
      result.current.setPage(2)
    })
    act(() => {
      result.current.setTotal(100)
    })
    expect(result.current.total).toBe(100)
    expect(result.current.page).toBe(2)
  })
})

describe('usePagination — offset 计算', () => {
  it('page=1 时 offset=0', () => {
    const { result } = renderHook(() => usePagination(20))
    expect(result.current.offset).toBe(0)
  })

  it('page=2, pageSize=20 时 offset=20', () => {
    const { result } = renderHook(() => usePagination(20))
    act(() => {
      result.current.setPage(2)
    })
    expect(result.current.offset).toBe(20)
  })

  it('page=3, pageSize=10 时 offset=20', () => {
    const { result } = renderHook(() => usePagination(10))
    act(() => {
      result.current.setPage(3)
    })
    expect(result.current.offset).toBe(20)
  })
})
