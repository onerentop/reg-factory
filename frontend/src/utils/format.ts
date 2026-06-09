export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleString('zh-CN')
}

export function formatDuration(ms: number | null | undefined): string {
  if (!ms) return '-'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function truncate(str: string, maxLen: number = 20): string {
  if (str.length <= maxLen) return str
  return str.slice(0, maxLen) + '...'
}

export function formatBalance(amount: number): string {
  return `$${amount.toFixed(2)}`
}
