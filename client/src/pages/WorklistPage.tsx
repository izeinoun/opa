import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Search, ChevronLeft, ChevronRight, SlidersHorizontal, X, UserPlus, Archive, ChevronDown } from 'lucide-react'
import { useCases } from '../hooks/useCases'
import { useDebounce } from '../hooks/useDebounce'
import { useCurrentUser } from '../hooks/useCurrentUser'
import CaseRow from '../components/cases/CaseRow'
import api from '../services/api'
import { card } from '../utils/designSystem'
import type { CaseStatus, LOB, WorklistFilters } from '../types'

const LOB_OPTIONS: { value: LOB | ''; label: string }[] = [
  { value: '', label: 'All LOBs' },
  { value: 'MA', label: 'MA' },
  { value: 'PPO', label: 'PPO' },
  { value: 'Medicaid', label: 'Medicaid' },
]

const DETECTOR_OPTIONS: { value: string; label: string }[] = [
  { value: '',       label: 'All issues'              },
  { value: 'DET-01', label: 'DET-01 — Duplicate Payment'      },
  { value: 'DET-02', label: 'DET-02 — Retro Eligibility'      },
  { value: 'DET-04', label: 'DET-04 — Fee Schedule Mispricing'},
  { value: 'DET-06', label: 'DET-06 — NCCI / MUE Violation'   },
  { value: 'DET-08', label: 'DET-08 — Excluded Provider'      },
  { value: 'DET-09', label: 'DET-09 — Coding Errors'          },
]

const PAGE_SIZE = 20

// Worklist scope: just my assigned cases, the unassigned pickup pool, or all.
type Scope = 'mine' | 'unassigned' | 'all'

// Lifecycle stages — each rolls up the granular statuses for that phase of the
// case journey. Drives both the tab strip here and the left-nav stage items.
type Stage = { key: string; label: string; statuses?: CaseStatus[]; overdue?: boolean; supervisorOnly?: boolean }
const STAGES: Stage[] = [
  { key: 'all',       label: 'All active' },
  { key: 'intake',    label: 'Intake',          statuses: ['new', 'awaiting_837'] },
  { key: 'review',    label: 'Review',          statuses: ['assigned', 'in_review', 'ready_for_notice'] },
  { key: 'approvals', label: 'Approvals',       statuses: ['pending_supervisor'], supervisorOnly: true },
  { key: 'recovery',  label: 'Recovery',        statuses: ['notice_sent', 'provider_responded', 'reconciling'] },
  { key: 'jeopardy',  label: '⚠ Jeopardy',      overdue: true },
]

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
  const queryClient = useQueryClient()
  const { currentUser, users } = useCurrentUser()
  const isSupervisor = currentUser?.role === 'supervisor' || currentUser?.role === 'admin'

  const [searchParams, setSearchParams] = useSearchParams()
  const stageKey = searchParams.get('stage') ?? 'all'
  const stage = STAGES.find((s) => s.key === stageKey) ?? STAGES[0]
  function setStage(key: string) {
    setSearchParams(key === 'all' ? {} : { stage: key })
    setPage(1)
    setSelected(new Set())
  }

  const [lob,     setLob]     = useState<LOB | ''>('')
  const [detectorCode, setDetectorCode] = useState<string>('')
  const [assigneeId, setAssigneeId] = useState<string>('')
  const [scope, setScope] = useState<Scope>(() => {
    const v = localStorage.getItem('opa_worklist_scope')
    return v === 'all' || v === 'unassigned' ? v : 'mine'
  })
  useEffect(() => { localStorage.setItem('opa_worklist_scope', scope) }, [scope])
  const [search,  setSearch]  = useState('')
  const [page,    setPage]    = useState(1)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [showAssignMenu, setShowAssignMenu] = useState(false)
  const debouncedSearch = useDebounce(search)
  useEffect(() => { setPage(1); setSelected(new Set()) }, [debouncedSearch])
  // Nav clicks change ?stage= while already on this page — keep paging in sync.
  useEffect(() => { setPage(1); setSelected(new Set()) }, [stageKey])

  const toggleSelect = (caseSeq: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(caseSeq)) next.delete(caseSeq); else next.add(caseSeq)
      return next
    })
  }

  const bulkAssignMut = useMutation({
    mutationFn: async (analyst_id: string) =>
      api.post('/cases/bulk-assign', { case_ids: Array.from(selected), analyst_id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cases'] })
      setSelected(new Set()); setShowAssignMenu(false)
    },
  })
  const bulkCloseMut = useMutation({
    mutationFn: async () =>
      api.post('/cases/bulk-close', { case_ids: Array.from(selected), reason: 'Bulk written-off via worklist' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cases'] })
      setSelected(new Set())
    },
  })

  const hasFilters = !!(lob || detectorCode || assigneeId || search)

  const filters: WorklistFilters = {
    page, page_size: PAGE_SIZE,
    exclude_closed: true,
    ...(stage.statuses ? { statuses: stage.statuses } : {}),
    ...(stage.overdue  ? { overdue_only: true }       : {}),
    ...(lob     ? { lob }          : {}),
    ...(detectorCode ? { detector_code: detectorCode } : {}),
    // Scope drives the assignee filter; the explicit Assignee dropdown only
    // applies in 'all' scope (supervisors).
    ...(scope === 'mine' && currentUser?.id
      ? { assignee_id: currentUser.id }
      : scope === 'unassigned'
        ? { assignee_id: '__unassigned__' }
        : (assigneeId ? { assignee_id: assigneeId } : {})),
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
  }

  const { data, isLoading, error } = useCases(filters)
  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1

  // Scope toggle counts — reflect the current stage + filter context (just a
  // total, page_size:1) so each button shows how many cases it would surface.
  const countBase = (extra: Partial<WorklistFilters>): WorklistFilters => ({
    page: 1, page_size: 1, exclude_closed: true,
    ...(stage.statuses ? { statuses: stage.statuses } : {}),
    ...(stage.overdue  ? { overdue_only: true }       : {}),
    ...(lob ? { lob } : {}),
    ...(detectorCode ? { detector_code: detectorCode } : {}),
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
    ...extra,
  })
  const mineCount       = useCases(countBase(currentUser?.id ? { assignee_id: currentUser.id } : {})).data?.total
  const unassignedCount = useCases(countBase({ assignee_id: '__unassigned__' })).data?.total
  const allCount        = useCases(countBase({})).data?.total
  const scopeCounts: Record<Scope, number | undefined> = {
    mine: currentUser?.id ? mineCount : undefined,
    unassigned: unassignedCount,
    all: allCount,
  }

  function clearFilters() {
    setLob(''); setDetectorCode(''); setAssigneeId(''); setSearch(''); setPage(1)
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
      </div>

      {/* Lifecycle stage tabs — the case pipeline, left→right. Mirrors the
          left-nav stage items; each applies a multi-status filter. */}
      <div className="flex flex-wrap items-center gap-1 border-b border-gray-200">
        {STAGES.filter((s) => !s.supervisorOnly || isSupervisor).map((s) => {
          const active = stage.key === s.key
          return (
            <button
              key={s.key}
              onClick={() => setStage(s.key)}
              className={`px-3.5 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${
                active
                  ? 'border-[#FE017D] text-[#FE017D]'
                  : 'border-transparent text-gray-500 hover:text-gray-800'
              }`}
            >
              {s.label}
            </button>
          )
        })}
      </div>

      {/* Scope toggle (all users — analyst, supervisor, admin) */}
      <div className="inline-flex bg-gray-100 rounded-lg p-0.5 self-start">
        {([
          { v: 'mine',       label: 'My cases' },
          { v: 'unassigned', label: 'Unassigned' },
          { v: 'all',        label: 'All cases' },
        ] as const).map((opt) => {
          const count = scopeCounts[opt.v]
          const active = scope === opt.v
          return (
            <button
              key={opt.v}
              onClick={() => { setScope(opt.v); setPage(1); setSelected(new Set()) }}
              className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                active
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {opt.label}
              {count !== undefined && (
                <span className={`ml-1.5 ${active ? 'text-[#FE017D]' : 'text-gray-400'}`}>
                  {count}
                </span>
              )}
            </button>
          )
        })}
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
          value={lob}
          onChange={(v) => { setLob(v as LOB | ''); setPage(1) }}
          options={LOB_OPTIONS}
        />

        <Select
          value={detectorCode}
          onChange={(v) => { setDetectorCode(v); setPage(1) }}
          options={DETECTOR_OPTIONS}
        />

        {isSupervisor && scope === 'all' && (
          <Select
            value={assigneeId}
            onChange={(v) => { setAssigneeId(v); setPage(1) }}
            options={[
              { value: '',                label: 'All assignees' },
              { value: '__unassigned__',  label: '— Unassigned —' },
              ...users
                .filter((u) => u.role === 'analyst' && u.is_active)
                .sort((a, b) => a.full_name.localeCompare(b.full_name))
                .map((u) => ({ value: u.id, label: u.full_name })),
            ]}
          />
        )}

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

      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl p-4 text-sm">
          Failed to load cases. Please try again.
        </div>
      )}

      {/* Bulk action bar (supervisor only, when items selected) */}
      {isSupervisor && selected.size > 0 && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-2.5 flex items-center justify-between gap-3">
          <p className="text-sm font-semibold text-indigo-900">
            {selected.size} selected
          </p>
          <div className="flex items-center gap-2">
            <div className="relative">
              <button
                onClick={() => setShowAssignMenu((v) => !v)}
                disabled={bulkAssignMut.isPending}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold bg-white text-indigo-700 border border-indigo-200 rounded hover:bg-indigo-50 disabled:opacity-50"
              >
                <UserPlus className="w-3 h-3" />
                {bulkAssignMut.isPending ? 'Assigning…' : 'Bulk assign…'}
                <ChevronDown className="w-3 h-3" />
              </button>
              {showAssignMenu && (
                <div className="absolute right-0 mt-1 w-56 bg-white border border-gray-200 rounded-lg shadow-lg z-20 max-h-72 overflow-y-auto">
                  {users.filter((u) => u.role === 'analyst' && u.is_active).map((u) => (
                    <button
                      key={u.id}
                      onClick={() => bulkAssignMut.mutate(u.id)}
                      className="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-50 text-gray-800"
                    >
                      {u.full_name}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button
              onClick={() => {
                if (window.confirm(`Bulk-close ${selected.size} case(s) as written-off?`)) {
                  bulkCloseMut.mutate()
                }
              }}
              disabled={bulkCloseMut.isPending}
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold bg-white text-red-700 border border-red-200 rounded hover:bg-red-50 disabled:opacity-50"
            >
              <Archive className="w-3 h-3" />
              {bulkCloseMut.isPending ? 'Closing…' : 'Bulk close (written-off)'}
            </button>
            <button
              onClick={() => setSelected(new Set())}
              className="text-xs text-gray-600 hover:text-gray-900 px-2"
            >
              Clear
            </button>
          </div>
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
                  {isSupervisor && (
                    <th className="pl-4 pr-1 py-3 w-8"></th>
                  )}
                  {['Case #', 'Priority', 'Status', 'Assignee', 'Member', 'Main Issue', 'At Risk', 'Deadline'].map((h, i) => (
                    <th
                      key={h}
                      className={`px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider
                                  ${i >= 6 ? 'text-right' : 'text-left'}`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {!data?.items.length ? (
                  <tr>
                    <td colSpan={isSupervisor ? 9 : 8} className="px-4 py-14 text-center text-sm text-gray-400">
                      No cases match your filters.
                    </td>
                  </tr>
                ) : (
                  data.items.map((c) => (
                    <CaseRow
                      key={c.id}
                      case_={c}
                      onClick={() => navigate(`/cases/${c.id}`)}
                      showCheckbox={isSupervisor}
                      selected={selected.has(c.id)}
                      onToggleSelect={toggleSelect}
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
