import type { CaseSummary } from '../../types'
import StatusBadge from '../common/StatusBadge'
import DeadlineIndicator from '../common/DeadlineIndicator'
import { formatCurrency } from '../../utils/formatUtils'
import { daysUntil } from '../../utils/dateUtils'

interface Props {
  case_: CaseSummary
  onClick: () => void
  selected?: boolean
  onToggleSelect?: (caseSeq: number) => void
  showCheckbox?: boolean
}

export default function CaseRow({ case_, onClick, selected, onToggleSelect, showCheckbox }: Props) {
  const days = daysUntil(case_.deadline)
  const isUrgent = days !== null && days <= 3  // overdue (< 0) or within 3 days

  const pillCls = isUrgent
    ? 'bg-red-100 text-red-700 border border-red-200'
    : 'bg-gray-100 text-gray-600 border border-gray-200'

  return (
    <tr
      onClick={onClick}
      className={`cursor-pointer transition-colors ${
        selected ? 'bg-indigo-50 hover:bg-indigo-100' :
        isUrgent ? 'bg-red-50 hover:bg-red-100' : 'bg-white hover:bg-blue-50'
      }`}
    >
      {showCheckbox && (
        <td className="pl-4 pr-1 py-3" onClick={(e) => e.stopPropagation()}>
          <input
            type="checkbox"
            checked={!!selected}
            onChange={() => onToggleSelect?.(case_.id)}
            className="w-4 h-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-400 cursor-pointer"
          />
        </td>
      )}
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
      <td className="px-4 py-3 text-sm whitespace-nowrap">
        {case_.primary_detector_id ? (
          <span
            title={case_.primary_detector_name ?? ''}
            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-800 border border-amber-200 cursor-help"
          >
            <span className="font-mono font-semibold">{case_.primary_detector_id}</span>
            <span className="text-amber-700">{case_.primary_detector_name}</span>
          </span>
        ) : (
          <span className="text-gray-400">—</span>
        )}
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
