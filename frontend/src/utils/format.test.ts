import { describe, it, expect } from 'vitest'
import { formatDate, formatDuration, truncate, formatBalance } from '@/utils/format'

describe('formatDate', () => {
  it('null/undefined/空 → -', () => {
    expect(formatDate(null)).toBe('-')
    expect(formatDate(undefined)).toBe('-')
    expect(formatDate('')).toBe('-')
  })
  it('有效日期含年份', () => {
    expect(formatDate('2026-06-12T00:00:00Z')).toContain('2026')
  })
})

describe('formatDuration', () => {
  it('null/0 → -', () => {
    expect(formatDuration(null)).toBe('-')
    expect(formatDuration(0)).toBe('-')
  })
  it('<1000 → ms', () => {
    expect(formatDuration(500)).toBe('500ms')
  })
  it('>=1000 → 一位小数 s', () => {
    expect(formatDuration(2500)).toBe('2.5s')
    expect(formatDuration(1000)).toBe('1.0s')
  })
})

describe('truncate', () => {
  it('短串原样', () => {
    expect(truncate('abc', 20)).toBe('abc')
    expect(truncate('a'.repeat(20), 20)).toBe('a'.repeat(20))
  })
  it('超长截断 + ...', () => {
    expect(truncate('a'.repeat(25), 20)).toBe('a'.repeat(20) + '...')
  })
})

describe('formatBalance', () => {
  it('两位小数前缀 $', () => {
    expect(formatBalance(3.5)).toBe('$3.50')
    expect(formatBalance(0)).toBe('$0.00')
  })
})
