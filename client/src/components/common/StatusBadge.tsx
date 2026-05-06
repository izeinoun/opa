import type { CaseStatus } from '../../types'
import { statusColor, statusLabel } from '../../utils/priorityUtils'

interface Props {
  status: CaseStatus
  size?: 'sm' | 'md'
}

export default function StatusBadge({ status, size = 'md' }: Props) {
  const colorClass = statusColor(status)
  const sizeClass = size === 'sm' ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 text-sm'

  return (
    <span
      className={`inline-flex items-center font-medium rounded-full ${colorClass} ${sizeClass}`}
    >
      {statusLabel(status)}
    </span>
  )
}
