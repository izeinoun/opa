import { useState } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { ShieldAlert, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import api from '../../../services/api'
import type { ExcludedProvider, ExcludedProviderList } from '../../../types'

const PAGE_SIZE = 50

function providerName(p: ExcludedProvider): string {
  if (p.business_name) return p.business_name
  const parts = [p.last_name, p.first_name].filter(Boolean)
  return parts.length ? parts.join(', ') : '—'
}

export default function ExcludedProvidersPanel() {
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  const { data, isLoading, isFetching } = useQuery<ExcludedProviderList>({
    queryKey: ['admin', 'excluded-providers', search, page],
    queryFn: async () =>
      (await api.get<ExcludedProviderList>('/admin/excluded-providers', {
        params: { search: search || undefined, page, page_size: PAGE_SIZE },
      })).data,
    placeholderData: keepPreviousData,
  })

  const submitSearch = () => {
    setSearch(searchInput.trim())
    setPage(1)
  }

  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const rows = data?.items ?? []
  const from = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const to = Math.min(page * PAGE_SIZE, total)

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-5 py-3 border-b border-gray-200 bg-white flex items-center gap-3">
        <ShieldAlert className="w-4 h-4 text-[#FE017D]" />
        <h2 className="text-sm font-bold text-gray-900">Excluded Providers</h2>
        <span className="text-xs text-gray-400">
          OIG LEIE · {total.toLocaleString()} records · screened by DET-08 on NPI
        </span>
        <div className="ml-auto flex items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && submitSearch()}
              placeholder="Search NPI or name…"
              className="w-64 pl-8 pr-3 py-1.5 text-sm bg-gray-50 border border-gray-200 rounded-lg
                         focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]"
            />
          </div>
          <button
            onClick={submitSearch}
            className="px-3 py-1.5 text-xs font-medium bg-[#FE017D] text-white rounded-lg hover:bg-[#e5006f] transition-colors"
          >
            Search
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 min-h-0 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-gray-50 border-b border-gray-200 z-10">
            <tr className="text-left text-[11px] font-semibold uppercase tracking-wider text-gray-500">
              <th className="px-4 py-2.5">NPI</th>
              <th className="px-4 py-2.5">Name</th>
              <th className="px-4 py-2.5">Category / Specialty</th>
              <th className="px-4 py-2.5">Location</th>
              <th className="px-4 py-2.5">Excl. Type</th>
              <th className="px-4 py-2.5">Excl. Date</th>
              <th className="px-4 py-2.5">Reinstated</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading ? (
              [...Array(12)].map((_, i) => (
                <tr key={i} className="animate-pulse">
                  <td colSpan={7} className="px-4 py-3">
                    <div className="h-4 bg-gray-100 rounded" />
                  </td>
                </tr>
              ))
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-16 text-center text-sm text-gray-400">
                  {search ? `No excluded providers match “${search}”.` : 'No excluded providers loaded.'}
                </td>
              </tr>
            ) : (
              rows.map(p => (
                <tr key={p.excluded_provider_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-2.5 font-mono text-xs font-semibold text-gray-800">{p.npi}</td>
                  <td className="px-4 py-2.5 text-gray-800">{providerName(p)}</td>
                  <td className="px-4 py-2.5 text-gray-600 text-xs">
                    {[p.general_category, p.specialty].filter(Boolean).join(' · ') || '—'}
                  </td>
                  <td className="px-4 py-2.5 text-gray-600 text-xs">
                    {[p.city, p.state].filter(Boolean).join(', ') || '—'}
                  </td>
                  <td className="px-4 py-2.5">
                    {p.exclusion_type ? (
                      <span className="font-mono text-[11px] bg-red-50 text-red-700 px-1.5 py-0.5 rounded">
                        {p.exclusion_type}
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-4 py-2.5 text-gray-600 text-xs font-mono">{p.exclusion_date || '—'}</td>
                  <td className="px-4 py-2.5 text-xs font-mono">
                    {p.reinstate_date
                      ? <span className="text-green-700">{p.reinstate_date}</span>
                      : <span className="text-gray-300">—</span>}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination footer */}
      <div className="px-5 py-2.5 border-t border-gray-200 bg-white flex items-center justify-between text-xs text-gray-500">
        <span className={isFetching ? 'opacity-50' : ''}>
          {from.toLocaleString()}–{to.toLocaleString()} of {total.toLocaleString()}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <ChevronLeft className="w-3.5 h-3.5" /> Prev
          </button>
          <span className="font-medium text-gray-700">Page {page} / {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}
