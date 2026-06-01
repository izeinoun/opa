// Read-only members directory.
//
// Member records are shared reference data managed centrally from the IAM
// admin app. PayGuard analysts can search and inspect coverage status here
// for context while reviewing cases; create / edit / delete is restricted
// to admins and lives in IAM (port 5177 → Members tab).
//
// The underlying API still accepts writes; this UI just doesn't expose
// them. The backend enforces admin-only writes via require_role("admin").
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Users, Search, Info } from 'lucide-react'
import api from '../services/api'

interface MemberRecord {
  member_id: string
  member_number: string
  first_name: string
  last_name: string
  date_of_birth: string
  lob: string
  coverage_effective_date: string
  coverage_termination_date: string | null
  created_at: string
  updated_at: string
}

interface MemberListResponse {
  total: number
  items: MemberRecord[]
}

const LOBS = ['MA', 'PPO', 'Medicaid']

function coverageStatus(member: MemberRecord): { label: string; cls: string } {
  const today = new Date().toISOString().slice(0, 10)
  if (member.coverage_effective_date > today) {
    return { label: 'Not Yet Active', cls: 'bg-amber-100 text-amber-700 border border-amber-200' }
  }
  if (member.coverage_termination_date && member.coverage_termination_date <= today) {
    return { label: 'Terminated', cls: 'bg-red-100 text-red-700 border border-red-200' }
  }
  return { label: 'Active', cls: 'bg-green-100 text-green-700 border border-green-200' }
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function MembersPage() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [lobFilter, setLobFilter] = useState('')

  const PAGE_SIZE = 20

  const { data, isLoading } = useQuery<MemberListResponse>({
    queryKey: ['members', page, search, lobFilter],
    queryFn: async () => {
      const params: Record<string, string | number> = { page, page_size: PAGE_SIZE }
      if (search) params.search = search
      if (lobFilter) params.lob = lobFilter
      const res = await api.get<MemberListResponse>('/members', { params })
      return res.data
    },
    staleTime: 30_000,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div className="flex flex-col gap-6 max-w-6xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Members</h1>
        <p className="text-sm text-gray-500 mt-1">
          Reference view of member eligibility and coverage. Read-only.
        </p>
      </div>

      {/* Admin-managed banner */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 flex items-start gap-3">
        <Info className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
        <div className="text-xs text-blue-900">
          <span className="font-semibold">Centrally managed.</span>{' '}
          Member records are maintained by admins in the IAM admin app. To add,
          update, or remove a member, switch to{' '}
          <span className="font-mono text-[11px] bg-blue-100 px-1.5 py-0.5 rounded">
            IAM → Members
          </span>
          .
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
          <input
            type="text"
            placeholder="Search by name or member #…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            className="w-full pl-8 pr-3 py-2 text-sm border border-gray-200 rounded-lg
                       focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]
                       bg-gray-50 text-gray-800 transition-colors"
          />
        </div>

        <select
          value={lobFilter}
          onChange={(e) => { setLobFilter(e.target.value); setPage(1) }}
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-gray-50
                     text-gray-700 focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30"
        >
          <option value="">All LOBs</option>
          {LOBS.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>

        <span className="text-xs text-gray-400 ml-auto">{total} member{total !== 1 ? 's' : ''}</span>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Member #</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Name</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">DOB</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">LOB</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Plan Start</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Plan Expiry</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-sm text-gray-400">Loading…</td>
              </tr>
            )}
            {!isLoading && items.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-sm text-gray-400">
                  <Users className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                  No members found
                </td>
              </tr>
            )}
            {items.map((m) => {
              const status = coverageStatus(m)
              return (
                <tr key={m.member_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">{m.member_number}</td>
                  <td className="px-4 py-3 font-medium text-gray-900">{m.first_name} {m.last_name}</td>
                  <td className="px-4 py-3 text-gray-600">{formatDate(m.date_of_birth)}</td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700">
                      {m.lob}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{formatDate(m.coverage_effective_date)}</td>
                  <td className="px-4 py-3 text-gray-600">{formatDate(m.coverage_termination_date)}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${status.cls}`}>
                      {status.label}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between">
            <span className="text-xs text-gray-500">
              Page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
                className="px-3 py-1.5 text-xs border border-gray-200 rounded-lg text-gray-600
                           hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Previous
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1.5 text-xs border border-gray-200 rounded-lg text-gray-600
                           hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
