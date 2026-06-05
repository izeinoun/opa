import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle, RefreshCw, ExternalLink } from 'lucide-react'
import api from '../../../services/api'
import { formatDate } from '../../../utils/dateUtils'
import type { ReferenceDataFreshness } from '../../../types'

const SOURCE_META: Record<string, { description: string; url: string }> = {
  'CMS Fee Schedule': {
    description: 'Medicare Physician Fee Schedule rates published by CMS.',
    url: 'https://www.cms.gov/medicare/payment/fee-schedules/physician',
  },
  'OIG Exclusion List': {
    description: 'HHS OIG list of providers excluded from federal healthcare programs.',
    url: 'https://oig.hhs.gov/exclusions/',
  },
  'State Medicaid Rates': {
    description: 'State-specific Medicaid reimbursement rates.',
    url: 'https://www.medicaid.gov/',
  },
  'DMF Death Master File': {
    description: 'SSA Death Master File for post-death billing detection.',
    url: 'https://www.ntis.gov/ladmf/ladmf.xhtml',
  },
  'NPPES NPI Registry': {
    description: 'National Plan & Provider Enumeration System.',
    url: 'https://npiregistry.cms.hhs.gov/',
  },
  'CPT Code Crosswalk': {
    description: 'AMA CPT procedure code definitions and modifiers.',
    url: 'https://www.ama-assn.org/practice-management/cpt',
  },
  'NCCI Policy Manual': {
    description: 'CMS NCCI PTP and MUE edit tables.',
    url: 'https://www.cms.gov/medicare/coding-billing/national-correct-coding-initiative-ncci-edits/medicare-ncci-policy-manual',
  },
}

const STYLE: Record<string, string> = {
  fresh:    'bg-green-100 text-green-700 border-green-200',
  stale:    'bg-amber-100 text-amber-700 border-amber-200',
  critical: 'bg-red-100 text-red-700 border-red-200',
}

export default function ReferenceFreshnessPanel() {
  const qc = useQueryClient()
  const [refreshing, setRefreshing] = useState<string | null>(null)

  const { data: freshness = [], isLoading } = useQuery<ReferenceDataFreshness[]>({
    queryKey: ['admin', 'freshness'],
    queryFn: async () => (await api.get<ReferenceDataFreshness[]>('/admin/reference-freshness')).data,
  })

  const refreshMutation = useMutation({
    mutationFn: async (name: string) => {
      setRefreshing(name)
      return (await api.post(`/admin/reference-freshness/${encodeURIComponent(name)}/refresh`)).data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'freshness'] })
      qc.invalidateQueries({ queryKey: ['freshness-banner'] })
    },
    onSettled: () => setRefreshing(null),
  })

  const hasCritical = freshness.some(f => f.status === 'critical')
  const hasStale    = freshness.some(f => f.status === 'stale')

  return (
    <div className="space-y-4">
      {(hasCritical || hasStale) && (
        <div className={`rounded-xl border p-4 flex items-start gap-3 ${
          hasCritical ? 'bg-red-50 border-red-200 text-red-800' : 'bg-amber-50 border-amber-200 text-amber-800'
        }`}>
          <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <p className="text-sm font-semibold">
            {hasCritical
              ? 'Critical: one or more reference data sources are critically outdated.'
              : 'Warning: some reference data sources are stale.'}
          </p>
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-5 space-y-2 animate-pulse">
            {[...Array(6)].map((_, i) => <div key={i} className="h-11 bg-gray-100 rounded-lg" />)}
          </div>
        ) : (
          <table className="min-w-full divide-y divide-gray-100">
            <thead className="bg-gray-50">
              <tr>
                {['Source', 'Status', 'Last Refreshed', 'Next Due', ''].map(h => (
                  <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {freshness.map(f => (
                <tr key={f.source_name} className={
                  f.status === 'critical' ? 'bg-red-50/50' : f.status === 'stale' ? 'bg-amber-50/50' : ''
                }>
                  <td className="px-5 py-4">
                    <p className="text-sm font-semibold text-gray-900">{f.source_name}</p>
                    {SOURCE_META[f.source_name] && (
                      <>
                        <p className="text-xs text-gray-500 mt-0.5 max-w-xs">{SOURCE_META[f.source_name].description}</p>
                        <a href={SOURCE_META[f.source_name].url} target="_blank" rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-[#FE017D] hover:underline mt-1">
                          <ExternalLink className="w-3 h-3" />
                          {SOURCE_META[f.source_name].url.replace('https://', '')}
                        </a>
                      </>
                    )}
                  </td>
                  <td className="px-5 py-3.5">
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${STYLE[f.status]}`}>
                      {f.status === 'fresh' ? <CheckCircle className="w-3 h-3" /> : <AlertTriangle className="w-3 h-3" />}
                      {f.status.charAt(0).toUpperCase() + f.status.slice(1)}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-sm text-gray-600">{formatDate(f.last_updated)}</td>
                  <td className="px-5 py-3.5 text-sm text-gray-600">{formatDate(f.next_due)}</td>
                  <td className="px-5 py-3.5">
                    <button
                      onClick={() => refreshMutation.mutate(f.source_name)}
                      disabled={refreshing === f.source_name}
                      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors
                        ${f.status !== 'fresh'
                          ? 'border-[#FE017D] text-[#FE017D] hover:bg-[#FE017D]/5'
                          : 'border-gray-200 text-gray-500 hover:bg-gray-50'
                        } disabled:opacity-50`}
                    >
                      <RefreshCw className={`w-3 h-3 ${refreshing === f.source_name ? 'animate-spin' : ''}`} />
                      {refreshing === f.source_name ? 'Refreshing…' : 'Refresh'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
