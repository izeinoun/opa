import { daysUntil } from '../../utils/dateUtils'

interface Props {
  deadline: string | null
  showDays?: boolean
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function DeadlineIndicator({ deadline, showDays = true }: Props) {
  if (!deadline) {
    return <span className="text-gray-400 text-sm">—</span>
  }

  const days = daysUntil(deadline)

  if (days === null) {
    return <span className="text-gray-400 text-sm">—</span>
  }

  const dateLabel = formatDate(deadline)

  if (days < 0) {
    return (
      <div className="flex flex-col leading-tight">
        <span className="font-bold text-red-700 text-xs">OVERDUE</span>
        <span className="text-red-500 text-xs">{dateLabel}</span>
      </div>
    )
  }

  if (days <= 3) {
    return (
      <div className="flex flex-col leading-tight">
        <span className="font-semibold text-orange-600 text-xs">
          {days} day{days === 1 ? '' : 's'} left
        </span>
        <span className="text-orange-400 text-xs">{dateLabel}</span>
      </div>
    )
  }

  return (
    <div className="flex flex-col leading-tight">
      <span className="text-gray-700 text-xs">{dateLabel}</span>
      {showDays && (
        <span className="text-gray-400 text-xs">{days}d remaining</span>
      )}
    </div>
  )
}
