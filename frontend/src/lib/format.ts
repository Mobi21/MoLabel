/**
 * Shared formatting utilities used across pages.
 */

export function formatNumber(n: number): string {
  return n.toLocaleString()
}

export function relativeTime(iso: string): string {
  const now = Date.now()
  const then = new Date(iso).getTime()
  const diffMs = now - then
  const diffMin = Math.floor(diffMs / 60_000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${String(diffMin)}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${String(diffHr)}h ago`
  const diffDay = Math.floor(diffHr / 24)
  return `${String(diffDay)}d ago`
}

export function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}
