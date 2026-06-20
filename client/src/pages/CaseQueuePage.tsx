// Reusable status-filtered case queue (Sent / Recovered / Not for Recoup).
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import StatusBadge from '../components/common/StatusBadge'
import { formatCurrency } from '../utils/formatUtils'
import { getCases } from '../services/caseService'
import type { CaseStatus } from '../types'

interface Props {
  title: string
  subtitle: string
  statuses: CaseStatus[]
  emptyText: string
}

export default function CaseQueuePage({ title, subtitle, statuses, emptyText }: Props) {
  const navigate = useNavigate()
  const { data, isLoading, error } = useQuery({
    queryKey: ['case-queue', statuses.join(',')],
    queryFn: () => getCases({ statuses, page: 1, page_size: 100 }),
  })
  const items = data?.items ?? []

  return (
    <div className="flex flex-col gap-5">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          {data && (
            <span className="inline-flex items-center px-2.5 py-0.5 bg-gray-100 text-gray-600 text-sm font-semibold rounded-full border border-gray-200">
              {data.total.toLocaleString()}
            </span>
          )}
        </div>
        <p className="text-sm text-gray-500 mt-1">{subtitle}</p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 text-sm">
          Failed to load cases. Please try again.
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-5 space-y-2.5 animate-pulse">
            {[...Array(6)].map((_, i) => <div key={i} className="h-11 bg-gray-100 rounded-lg" />)}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-100">
              <thead className="bg-gray-50">
                <tr>
                  {['Case #', 'Status', 'Assignee', 'Member', 'Amount at Risk', 'Opened'].map((h, i) => (
                    <th key={h} className={`px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider ${i >= 4 ? 'text-right' : 'text-left'}`}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {!items.length ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-14 text-center text-sm text-gray-400">
                      {emptyText}
                    </td>
                  </tr>
                ) : (
                  items.map((c) => (
                    <tr
                      key={c.id}
                      onClick={() => navigate(`/cases/${c.id}`)}
                      className="cursor-pointer bg-white hover:bg-gray-50 transition-colors"
                    >
                      <td className="px-4 py-3 text-sm font-mono font-semibold text-gray-900 whitespace-nowrap">{c.case_number}</td>
                      <td className="px-4 py-3"><StatusBadge status={c.status} size="sm" /></td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {c.assignee?.full_name ?? <span className="text-gray-400">Unassigned</span>}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">
                        {c.claim?.member?.name ?? <span className="text-gray-400">—</span>}
                      </td>
                      <td className="px-4 py-3 text-sm font-semibold text-gray-900 text-right whitespace-nowrap">
                        {formatCurrency(c.amount_at_risk)}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 text-right whitespace-nowrap">
                        {c.opened_at ? new Date(c.opened_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
