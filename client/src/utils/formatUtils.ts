export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export function formatConfidence(score: number): string {
  if (score >= 0.8) return `High (${score.toFixed(2)})`
  if (score >= 0.6) return `Medium (${score.toFixed(2)})`
  return `Low (${score.toFixed(2)})`
}

export function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text
  return `${text.slice(0, maxLen - 3)}...`
}
