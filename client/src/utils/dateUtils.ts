export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  try {
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    })
  } catch {
    return '—'
  }
}

export function formatDateShort(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  try {
    const date = new Date(dateStr)
    const mm = String(date.getMonth() + 1).padStart(2, '0')
    const dd = String(date.getDate()).padStart(2, '0')
    const yy = String(date.getFullYear()).slice(2)
    return `${mm}/${dd}/${yy}`
  } catch {
    return '—'
  }
}

export function daysUntil(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null
  try {
    const target = new Date(dateStr)
    const now = new Date()
    // Zero out time to compare dates only
    target.setHours(0, 0, 0, 0)
    now.setHours(0, 0, 0, 0)
    const diff = target.getTime() - now.getTime()
    return Math.round(diff / (1000 * 60 * 60 * 24))
  } catch {
    return null
  }
}

export function daysAgo(dateStr: string): number {
  try {
    const past = new Date(dateStr)
    const now = new Date()
    past.setHours(0, 0, 0, 0)
    now.setHours(0, 0, 0, 0)
    const diff = now.getTime() - past.getTime()
    return Math.round(diff / (1000 * 60 * 60 * 24))
  } catch {
    return 0
  }
}

export function agingBucketLabel(openedAt: string): string {
  const days = daysAgo(openedAt)
  if (days <= 15) return '0-15d'
  if (days <= 30) return '16-30d'
  if (days <= 45) return '31-45d'
  if (days <= 60) return '46-60d'
  return '60+d'
}

export function isOverdue(deadline: string | null | undefined): boolean {
  if (!deadline) return false
  const days = daysUntil(deadline)
  return days !== null && days < 0
}

export function formatRelative(dateStr: string | null | undefined): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return ''
  const secs = Math.floor((Date.now() - d.getTime()) / 1000)
  if (secs < 60)         return 'just now'
  if (secs < 3600)       return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400)      return `${Math.floor(secs / 3600)}h ago`
  if (secs < 86400 * 7)  return `${Math.floor(secs / 86400)}d ago`
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}
