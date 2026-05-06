import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, ChevronLeft, ChevronRight, SlidersHorizontal, X } from 'lucide-react'
import { useCases } from '../hooks/useCases'
import { useDebounce } from '../hooks/useDebounce'
import CaseRow from '../components/cases/CaseRow'
import { card, priorityBadge } from '../utils/designSystem'
import type { CaseStatus, Priority, LOB, WorklistFilters } from '../types'

const STATUS_TABS: { value: CaseStatus | ''; label: string; activeClass: string; inactiveClass: string }[] = [
  { value: '',                    label: 'All',                activeClass: 'bg-gray-900 text-white',         inactiveClass: 'bg-gray-100 text-gray-600 hover:bg-gray-200'           },
  { value: 'new',                 label: 'New',                activeClass: 'bg-gray-800 text-white',         inactiveClass: 'bg-gray-100 text-gray-600 hover:bg-gray-200'           },
  { value: 'assigned',            label: 'Assigned',           activeClass: 'bg-blue-600 text-white',         inactiveClass: 'bg-blue-50 text-blue-700 hover:bg-blue-100'            },
  { value: 'in_review',           label: 'In Review',          activeClass: 'bg-amber-500 text-white',        inactiveClass: 'bg-amber-50 text-amber-700 hover:bg-amber-100'         },
  { value: 'pending_supervisor',  label: 'Pending Supervisor', activeClass: 'bg-purple-600 text-white',       inactiveClass: 'bg-purple-50 text-purple-700 hover:bg-purple-100'      },
  { value: 'notice_sent',         label: 'Notice Sent',        activeClass: 'bg-teal-600 text-white',         inactiveClass: 'bg-teal-50 text-teal-700 hover:bg-teal-100'            },
  { value: 'provider_responded',  label: 'Provider Responded', activeClass: 'bg-blue-500 text-white',         inactiveClass: 'bg-blue-50 text-blue-600 hover:bg-blue-100'            },
  { value: 'reconciling',         label: 'Reconciling',        activeClass: 'bg-amber-600 text-white',        inactiveClass: 'bg-amber-50 text-amber-700 hover:bg-amber-100'         },
]

const PRIORITY_OPTIONS: { value: Priority | ''; label: string }[] = [
  { value: '', label: 'All Priorities' },
  { value: 'HIGH', label: 'High' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'LOW', label: 'Low' },
]

const LOB_OPTIONS: { value: LOB | ''; label: string }[] = [
  { value: '', label: 'All LOBs' },
  { value: 'MA', label: 'MA' },
  { value: 'PPO', label: 'PPO' },
  { value: 'Medicaid', label: 'Medicaid' },
]

const PAGE_SIZE = 20

function Select({
  value, onChange, options, className = '',
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  className?: string
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm
                  text-gray-700 focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30
                  focus:border-[#FE017D] transition-colors ${className}`}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  )
}

export default function WorklistPage() {
  const navigate = useNavigate()
  const [status,   setStatus]   = useState<CaseStatus | ''>('')
  const [priority, setPriority] = useState<Priority | ''>('')
  const [lob,      setLob]      = useState<LOB | ''>('')
  const [search,   setSearch]   = useState('')
  const [page,     setPage]     = useState(1)
  const debouncedSearch = useDebounce(search)
  useEffect(() => { setPage(1) }, [debouncedSearch])

  const hasFilters = !!(priority || lob || search)

  const filters: WorklistFilters = {
    page, page_size: PAGE_SIZE,
    exclude_closed: true,
    ...(status   ? { status }   : {}),
    ...(priority ? { priority } : {}),
    ...(lob      ? { lob }      : {}),
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
  }

  const { data, isLoading, error } = useCases(filters)
  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1

  function clearFilters() {
    setPriority(''); setLob(''); setSearch(''); setPage(1)
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Header + status tabs */}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold text-gray-900">Case Worklist</h1>
        {data && (
          <span className="inline-flex items-center px-2.5 py-0.5
                           bg-[#FE017D]/10 text-[#FE017D]
                           text-sm font-semibold rounded-full border border-[#FE017D]/20">
            {data.total.toLocaleString()}
          </span>
        )}
        <div className="flex flex-wrap items-center gap-1.5 ml-1">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => { setStatus(tab.value); setPage(1) }}
              className={`px-3 py-1 rounded-full text-xs font-semibold transition-colors ${
                status === tab.value ? tab.activeClass : tab.inactiveClass
              }`}
            >
              {tab.label}
            </button>
          ))}
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
          value={priority}
          onChange={(v) => { setPriority(v as Priority | ''); setPage(1) }}
          options={PRIORITY_OPTIONS}
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

        {priority && (
          <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium border ${priorityBadge[priority.toLowerCase() as keyof typeof priorityBadge]}`}>
            {priority}
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
                  {['Case #', 'Score', 'Status', 'Assignee', 'Member', 'At Risk', 'Deadline'].map((h, i) => (
                    <th
                      key={h}
                      className={`px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider
                                  ${i >= 5 ? 'text-right' : 'text-left'}`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {!data?.items.length ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-14 text-center text-sm text-gray-400">
                      No cases match your filters.
                    </td>
                  </tr>
                ) : (
                  data.items.map((c) => (
                    <CaseRow
                      key={c.id}
                      case_={c}
                      onClick={() => navigate(`/cases/${c.id}`)}
                    />
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
