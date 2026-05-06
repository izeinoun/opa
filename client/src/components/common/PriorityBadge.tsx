import type { Priority } from '../../types'
import { priorityColor } from '../../utils/priorityUtils'

interface Props {
  priority: Priority
  size?: 'sm' | 'md'
}

export default function PriorityBadge({ priority, size = 'md' }: Props) {
  const colorClass = priorityColor(priority)
  const sizeClass = size === 'sm' ? 'px-1.5 py-0.5 text-xs' : 'px-2.5 py-1 text-sm'

  return (
    <span
      className={`inline-flex items-center font-semibold rounded-full ${colorClass} ${sizeClass}`}
    >
      {priority}
    </span>
  )
}
