import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight, SlidersHorizontal, X, Search } from 'lucide-react'
import { useCases } from '../hooks/useCases'
import { useDebounce } from '../hooks/useDebounce'
import { card, statusBadge } from '../utils/designSystem'
import StatusBadge from '../components/common/StatusBadge'
import { formatCurrency } from '../utils/formatUtils'
import type { CaseStatus, LOB, WorklistFilters } from '../types'

const STATUS_OPTIONS: { value: CaseStatus | ''; label: string }[] = [
  { value: '', label: 'All Closed' },
  { value: 'closed_recovered', label: 'Recovered' },
  { value: 'closed_not_for_recoup', label: 'Not for Recoup' },
  { value: 'closed_written_off', label: 'Written Off' },
  { value: 'closed_overturned', label: 'Overturned' },
  { value: 'closed_no_overpayment', label: 'No Overpayment' },
  { value: 'closed_unrecoverable', label: 'Unrecoverable' },
]

const LOB_OPTIONS: { value: LOB | ''; label: string }[] = [
  { value: '', label: 'All LOBs' },
  { value: 'MA', label: 'MA' },
  { value: 'PPO', label: 'PPO' },
  { value: 'Medicaid', label: 'Medicaid' },
]

const PAGE_SIZE = 20

function Select({
  value, onChange, options,
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm
                 text-gray-700 focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30
                 focus:border-[#FE017D] transition-colors"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  )
}

export default function ClosedCasesPage() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<CaseStatus | ''>('')
  const [lob,    setLob]    = useState<LOB | ''>('')
  const [search, setSearch] = useState('')
  const [page,   setPage]   = useState(1)
  const debouncedSearch = useDebounce(search)
  useEffect(() => { setPage(1) }, [debouncedSearch])

  const hasFilters = !!(status || lob || search)

  const filters: WorklistFilters = {
    page, page_size: PAGE_SIZE,
    closed_only: true,
    ...(status          ? { status }                      : {}),
    ...(lob             ? { lob }                         : {}),
    ...(debouncedSearch ? { search: debouncedSearch }     : {}),
  }

  const { data, isLoading, error } = useCases(filters)
  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1

  function clearFilters() {
    setStatus(''); setLob(''); setSearch(''); setPage(1)
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-gray-900">Closed Cases</h1>
          {data && (
            <span className="inline-flex items-center px-2.5 py-0.5
                             bg-gray-100 text-gray-600
                             text-sm font-semibold rounded-full border border-gray-200">
              {data.total.toLocaleString()}
            </span>
          )}
        </div>
      </div>

      {/* Filter bar */}
      <div className={`${card} flex flex-wrap gap-3 items-center`}>
        <SlidersHorizontal className="w-4 h-4 text-gray-400 flex-shrink-0" />

        <div className="relative flex-1 min-w-[180px] max-w-xs">
          <Search className="absolute left-2.5 top-2.5 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by member name or case #…"
            className="w-full pl-8 pr-3 py-2 bg-gray-50 border border-gray-200 rounded-lg
                       text-sm focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30
                       focus:border-[#FE017D] transition-colors"
          />
        </div>

        <Select
          value={status}
          onChange={(v) => { setStatus(v as CaseStatus | ''); setPage(1) }}
          options={STATUS_OPTIONS}
        />
        <Select
          value={lob}
          onChange={(v) => { setLob(v as LOB | ''); setPage(1) }}
          options={LOB_OPTIONS}
        />

        {hasFilters && (
          <button
            onClick={clearFilters}
            className="inline-flex items-center gap-1 px-2.5 py-2 text-xs
                       text-gray-500 hover:text-gray-700 bg-gray-100 hover:bg-gray-200
                       rounded-lg transition-colors"
          >
            <X className="w-3 h-3" /> Clear
          </button>
        )}

        {status && (
          <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium ${statusBadge[status] ?? 'bg-gray-100 text-gray-600'}`}>
            {STATUS_OPTIONS.find((o) => o.value === status)?.label}
          </span>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 text-sm">
          Failed to load cases. Please try again.
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-5 space-y-2.5 animate-pulse">
            {[...Array(8)].map((_, i) => (
              <div key={i} className="h-11 bg-gray-100 rounded-lg" />
            ))}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-100">
              <thead className="bg-gray-50">
                <tr>
                  {['Case #', 'Outcome', 'Assignee', 'Member', 'Amount at Risk', 'Opened'].map((h, i) => (
                    <th
                      key={h}
                      className={`px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider
                                  ${i >= 4 ? 'text-right' : 'text-left'}`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {!data?.items.length ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-14 text-center text-sm text-gray-400">
                      No closed cases found.
                    </td>
                  </tr>
                ) : (
                  data.items.map((c) => (
                    <tr
                      key={c.id}
                      onClick={() => navigate(`/cases/${c.id}`)}
                      className="cursor-pointer bg-white hover:bg-gray-50 transition-colors"
                    >
                      <td className="px-4 py-3 text-sm font-mono font-semibold text-gray-900 whitespace-nowrap">
                        {c.case_number}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={c.status} size="sm" />
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {c.assignee?.full_name ?? <span className="text-gray-400">Unassigned</span>}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">
                        {c.claim.member?.name ?? <span className="text-gray-400">—</span>}
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

      {/* Pagination */}
      {data && data.total > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-gray-500">
            Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, data.total)} of{' '}
            {data.total.toLocaleString()} cases
          </p>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-1.5 rounded-lg border border-gray-200 text-gray-600
                         hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed
                         transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="px-3 py-1.5 text-sm text-gray-700 bg-white border border-gray-200 rounded-lg">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-1.5 rounded-lg border border-gray-200 text-gray-600
                         hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed
                         transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
