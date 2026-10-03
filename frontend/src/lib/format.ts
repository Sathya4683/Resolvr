const TZ = 'Asia/Kolkata'

export function dayKey(iso: string) {
  return new Date(iso).toLocaleDateString('en-CA', { timeZone: TZ })
}

//"Today", "Yesterday" or "Thu, 1 Oct" like the chatgpt sidebar
export function dayLabel(iso: string) {
  const key = dayKey(iso)
  const today = dayKey(new Date().toISOString())
  const yesterday = dayKey(new Date(Date.now() - 86_400_000).toISOString())
  if (key === today) return 'Today'
  if (key === yesterday) return 'Yesterday'
  return new Date(iso).toLocaleDateString('en-IN', { timeZone: TZ, weekday: 'short', day: 'numeric', month: 'short' })
}

export function timeOf(iso: string) {
  return new Date(iso).toLocaleTimeString('en-IN', { timeZone: TZ, hour: 'numeric', minute: '2-digit' })
}

export function dateTime(iso: string) {
  return new Date(iso).toLocaleString('en-IN', {
    timeZone: TZ,
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function timeAgo(iso: string) {
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export function titleCase(s: string | null | undefined) {
  if (!s) return ''
  return s
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bDth\b/g, 'DTH')
}

export function pct(n: number | null | undefined, digits = 0) {
  if (n === null || n === undefined) return '-'
  return `${(n * 100).toFixed(digits)}%`
}
