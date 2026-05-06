import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Building2, FileSpreadsheet, AlertCircle } from 'lucide-react'
import api from '../services/api'
import { formatCurrency } from '../utils/formatUtils'

interface OrgSummary {
  provider_org_id: string
  name: string
  npi: string
  org_type: string
  schedule_count: number
  lobs: string[]
}

interface FeeScheduleRow {
  fee_schedule_id: string
  lob: string
  cpt_code: string
  cpt_description: string | null
  effective_date: string
  termination_date: string | null
  base_rate: number
  rate_basis: string
  modifier_applicable: string | null
}

interface ContractLimitationRow {
  limitation_id: string
  cpt_code: string
  limitation_type: string
  limitation_value: string
  effective_date: string
  description: string
}

interface OrgDetail {
  provider_org_id: string
  name: string
  npi: string
  tin: string
  org_type: string
  fee_schedules: FeeScheduleRow[]
  contract_limitations: ContractLimitationRow[]
}

const LOB_COLOR: Record<string, string> = {
  MA:       'bg-blue-100 text-blue-700',
  PPO:      'bg-purple-100 text-purple-700',
  Medicaid: 'bg-green-100 text-green-700',
}

async function fetchOrgs(): Promise<OrgSummary[]> {
  const res = await api.get<OrgSummary[]>('/fee-schedules')
  return res.data
}

async function fetchDetail(id: string): Promise<OrgDetail> {
  const res = await api.get<OrgDetail>(`/fee-schedules/${id}`)
  return res.data
}

export default function FeeSchedulesPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [activeLob, setActiveLob]   = useState<string>('All')

  const { data: orgs = [], isLoading: orgsLoading } = useQuery<OrgSummary[]>({
    queryKey: ['fee-schedule-orgs'],
    queryFn: async () => {
      const data = await fetchOrgs()
      if (data.length && !selectedId) setSelectedId(data[0].provider_org_id)
      return data
    },
  })

  const { data: detail } = useQuery<OrgDetail>({
    queryKey: ['fee-schedule-detail', selectedId],
    queryFn: () => fetchDetail(selectedId!),
    enabled: !!selectedId,
  })

  const allLobs = detail ? ['All', ...Array.from(new Set(detail.fee_schedules.map(r => r.lob))).sort()] : ['All']
  const rows = detail?.fee_schedules.filter(r => activeLob === 'All' || r.lob === activeLob) ?? []

  const cptCodes = Array.from(new Set(rows.map(r => r.cpt_code))).sort()

  return (
    <div className="flex flex-col gap-6 max-w-7xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Fee Schedules</h1>
        <p className="text-sm text-gray-500 mt-1">
          Contracted rates by provider organisation, CPT code, and line of business.
        </p>
      </div>

      <div className="flex gap-5 items-start">

        {/* Org list */}
        <div className="w-64 flex-shrink-0 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
            <Building2 className="w-4 h-4 text-gray-400" />
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Provider Orgs</span>
          </div>
          {orgsLoading ? (
            <div className="p-4 space-y-2">
              {[1,2,3].map(i => <div key={i} className="h-10 bg-gray-100 rounded-lg animate-pulse" />)}
            </div>
          ) : (
            <ul className="py-1">
              {orgs.map(org => (
                <li key={org.provider_org_id}>
                  <button
                    onClick={() => { setSelectedId(org.provider_org_id); setActiveLob('All') }}
                    className={`w-full text-left px-4 py-3 transition-colors ${
                      selectedId === org.provider_org_id
                        ? 'bg-pink-50 border-l-2 border-[#FE017D]'
                        : 'hover:bg-gray-50 border-l-2 border-transparent'
                    }`}
                  >
                    <p className={`text-sm font-semibold truncate ${selectedId === org.provider_org_id ? 'text-[#FE017D]' : 'text-gray-800'}`}>
                      {org.name}
                    </p>
                    <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                      {org.lobs.map(lob => (
                        <span key={lob} className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${LOB_COLOR[lob] ?? 'bg-gray-100 text-gray-600'}`}>
                          {lob}
                        </span>
                      ))}
                      <span className="text-[10px] text-gray-400 ml-auto">{org.schedule_count} rates</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Detail panel */}
        <div className="flex-1 min-w-0 space-y-4">
          {!detail ? (
            <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400">
              <FileSpreadsheet className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p className="text-sm">Select a provider org to view its fee schedule</p>
            </div>
          ) : (
            <>
              {/* Org header */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-5 py-4">
                <div className="flex items-start justify-between">
                  <div>
                    <h2 className="text-base font-bold text-gray-900">{detail.name}</h2>
                    <p className="text-xs text-gray-400 mt-0.5 font-mono">NPI {detail.npi} · TIN {detail.tin}</p>
                  </div>
                  <span className="text-xs font-semibold bg-gray-100 text-gray-600 px-2 py-1 rounded-lg capitalize">
                    {detail.org_type}
                  </span>
                </div>
              </div>

              {/* LOB tabs */}
              <div className="flex gap-1">
                {allLobs.map(lob => (
                  <button
                    key={lob}
                    onClick={() => setActiveLob(lob)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                      activeLob === lob
                        ? 'bg-[#FE017D] text-white'
                        : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    {lob}
                  </button>
                ))}
              </div>

              {/* Fee schedule table */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 border-b border-gray-200">
                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">CPT</th>
                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Description</th>
                        {activeLob === 'All' && (
                          <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">LOB</th>
                        )}
                        <th className="text-right px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Base Rate</th>
                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Basis</th>
                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Effective</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {cptCodes.map(cpt => {
                        const cptRows = rows.filter(r => r.cpt_code === cpt)
                        return cptRows.map((row, idx) => (
                          <tr key={row.fee_schedule_id} className="hover:bg-gray-50 transition-colors">
                            {idx === 0 ? (
                              <td rowSpan={cptRows.length} className="px-4 py-3 align-top">
                                <span className="font-mono font-semibold text-gray-800">{cpt}</span>
                              </td>
                            ) : null}
                            {idx === 0 ? (
                              <td rowSpan={cptRows.length} className="px-4 py-3 align-top text-xs text-gray-500 max-w-xs">
                                {row.cpt_description ?? '—'}
                              </td>
                            ) : null}
                            {activeLob === 'All' && (
                              <td className="px-4 py-2.5">
                                <span className={`text-xs font-bold px-1.5 py-0.5 rounded-full ${LOB_COLOR[row.lob] ?? 'bg-gray-100 text-gray-600'}`}>
                                  {row.lob}
                                </span>
                              </td>
                            )}
                            <td className="px-4 py-2.5 text-right font-semibold text-gray-900">
                              {formatCurrency(row.base_rate)}
                            </td>
                            <td className="px-4 py-2.5 text-xs text-gray-500">{row.rate_basis}</td>
                            <td className="px-4 py-2.5 text-xs text-gray-400 font-mono">{row.effective_date}</td>
                          </tr>
                        ))
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Contract limitations */}
              {detail.contract_limitations.length > 0 && (
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                  <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-amber-400" />
                    <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Contract Limitations</span>
                  </div>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 border-b border-gray-200">
                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">CPT</th>
                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Type</th>
                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Value</th>
                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Description</th>
                        <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wider">Effective</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {detail.contract_limitations.map(lim => (
                        <tr key={lim.limitation_id} className="hover:bg-gray-50">
                          <td className="px-4 py-2.5 font-mono font-semibold text-gray-800">{lim.cpt_code}</td>
                          <td className="px-4 py-2.5">
                            <span className="text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-100 px-2 py-0.5 rounded-full">
                              {lim.limitation_type}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-xs font-semibold text-gray-700">{lim.limitation_value}</td>
                          <td className="px-4 py-2.5 text-xs text-gray-500">{lim.description}</td>
                          <td className="px-4 py-2.5 text-xs text-gray-400 font-mono">{lim.effective_date}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
