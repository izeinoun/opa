import type { CaseSummary } from '../../types'
import StatusBadge from '../common/StatusBadge'
import DeadlineIndicator from '../common/DeadlineIndicator'
import { formatCurrency } from '../../utils/formatUtils'
import { daysUntil } from '../../utils/dateUtils'

interface Props {
  case_: CaseSummary
  onClick: () => void
}

export default function CaseRow({ case_, onClick }: Props) {
  const days = daysUntil(case_.deadline)
  const isUrgent = days !== null && days <= 3  // overdue (< 0) or within 3 days

  const pillCls = isUrgent
    ? 'bg-red-100 text-red-700 border border-red-200'
    : 'bg-gray-100 text-gray-600 border border-gray-200'

  return (
    <tr
      onClick={onClick}
      className={`cursor-pointer transition-colors ${
        isUrgent ? 'bg-red-50 hover:bg-red-100' : 'bg-white hover:bg-blue-50'
      }`}
    >
      <td className="px-4 py-3 text-sm font-mono font-semibold text-gray-900 whitespace-nowrap">
        {case_.case_number}
      </td>
      <td className="px-4 py-3">
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold tabular-nums ${pillCls}`}>
          {case_.priority_score.toFixed(1)}
        </span>
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={case_.status} size="sm" />
      </td>
      <td className="px-4 py-3 text-sm text-gray-600">
        {case_.assignee?.full_name ?? <span className="text-gray-400">Unassigned</span>}
      </td>
      <td className="px-4 py-3 text-sm text-gray-700">
        {case_.claim.member?.name ?? <span className="text-gray-400">—</span>}
      </td>
      <td className="px-4 py-3 text-sm font-semibold text-gray-900 text-right whitespace-nowrap">
        {formatCurrency(case_.amount_at_risk)}
      </td>
      <td className="px-4 py-3 text-sm">
        <DeadlineIndicator deadline={case_.deadline} showDays={true} />
      </td>
    </tr>
  )
}
