import type { AuditLog } from '../../types'
import { statusLabel } from '../../utils/priorityUtils'
import type { CaseStatus } from '../../types'

interface Props {
  logs: AuditLog[]
}

function relativeTime(dateStr: string): string {
  const now = new Date()
  const past = new Date(dateStr)
  const diffMs = now.getTime() - past.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHr = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHr / 24)

  if (diffSec < 60) return 'just now'
  if (diffMin < 60) return `${diffMin} minute${diffMin === 1 ? '' : 's'} ago`
  if (diffHr < 24) return `${diffHr} hour${diffHr === 1 ? '' : 's'} ago`
  if (diffDay < 30) return `${diffDay} day${diffDay === 1 ? '' : 's'} ago`
  const diffMonth = Math.floor(diffDay / 30)
  return `${diffMonth} month${diffMonth === 1 ? '' : 's'} ago`
}

function isCaseStatus(s: string | null): s is CaseStatus {
  return s !== null && [
    'new', 'assigned', 'in_review', 'pending_supervisor',
    'notice_sent', 'provider_responded', 'reconciling',
    'closed_recovered', 'closed_written_off', 'closed_overturned', 'closed_no_overpayment',
  ].includes(s)
}

export default function AuditTimeline({ logs }: Props) {
  const sorted = [...logs].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  )

  if (sorted.length === 0) {
    return <p className="text-sm text-gray-400 py-4 text-center">No audit history.</p>
  }

  return (
    <ol className="relative border-l border-gray-200 ml-3 space-y-6">
      {sorted.map((log) => (
        <li key={log.id} className="ml-4">
          <div className="absolute -left-1.5 w-3 h-3 bg-opa-500 rounded-full border-2 border-white mt-1" />
          <div className="bg-white border border-gray-100 rounded-lg p-3 shadow-sm">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-semibold text-gray-700">
                {log.user?.full_name ?? 'System'}
              </span>
              <time className="text-xs text-gray-400">{relativeTime(log.created_at)}</time>
            </div>
            <p className="text-sm font-medium text-gray-800">{log.action}</p>
            {log.from_status && log.to_status && (
              <div className="mt-1 flex items-center gap-1.5 text-xs text-gray-500">
                <span className="px-1.5 py-0.5 rounded bg-gray-100 font-mono">
                  {isCaseStatus(log.from_status)
                    ? statusLabel(log.from_status)
                    : log.from_status}
                </span>
                <span className="text-gray-400">→</span>
                <span className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 font-mono">
                  {isCaseStatus(log.to_status)
                    ? statusLabel(log.to_status)
                    : log.to_status}
                </span>
              </div>
            )}
            {log.notes && (
              <p className="mt-1.5 text-xs text-gray-500 italic">"{log.notes}"</p>
            )}
          </div>
        </li>
      ))}
    </ol>
  )
}
