import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ShieldAlert, TrendingUp, TrendingDown, FileText, ChevronDown, ChevronRight } from 'lucide-react'
import api from '../services/api'
import { useCurrentUser } from '../hooks/useCurrentUser'

interface DriverFactor {
  feature: string
  label: string
  provider_value: number
  provider_value_fmt: string
  population_mean: number
  population_mean_fmt: string
  shap_contribution: number
  direction: 'raises' | 'lowers' | 'neutral'
}

interface ProviderRiskExplanation {
  npi: string
  name: string
  specialty: string
  score: number
  band: 'HIGH' | 'MEDIUM' | 'LOW'
  top_drivers: DriverFactor[]
  plain_english: string
  n_claims_in_system: number
}

const BAND_COLOR: Record<string, string> = {
  HIGH:   'bg-red-100 text-red-700 border-red-200',
  MEDIUM: 'bg-amber-100 text-amber-800 border-amber-200',
  LOW:    'bg-green-100 text-green-700 border-green-200',
}

const BAND_BAR: Record<string, string> = {
  HIGH:   'bg-red-500',
  MEDIUM: 'bg-amber-500',
  LOW:    'bg-green-500',
}

export default function ProviderRiskPage() {
  const { currentUser } = useCurrentUser()
  const isSupervisor = currentUser?.role === 'supervisor' || currentUser?.role === 'admin'
  const [expanded, setExpanded] = useState<string | null>(null)
  const [bandFilter, setBandFilter] = useState<'ALL' | 'HIGH' | 'MEDIUM' | 'LOW'>('ALL')

  const { data: items = [], isLoading, error } = useQuery<ProviderRiskExplanation[]>({
    queryKey: ['provider-risk'],
    queryFn: async () => (await api.get<ProviderRiskExplanation[]>('/provider-risk')).data,
    enabled: isSupervisor,
  })

  if (!isSupervisor) {
    return (
      <div className="max-w-3xl">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">Provider Risk</h1>
        <div className="bg-white border border-gray-200 rounded-xl p-8 text-center">
          <ShieldAlert className="w-10 h-10 text-gray-300 mx-auto mb-2" />
          <p className="text-sm font-semibold text-gray-700">Supervisor or admin access required</p>
          <p className="text-xs text-gray-500 mt-1">
            This page explains the model's score for each provider, including which features drove it.
          </p>
        </div>
      </div>
    )
  }

  const filtered = bandFilter === 'ALL' ? items : items.filter((p) => p.band === bandFilter)
  const highCount = items.filter((p) => p.band === 'HIGH').length

  return (
    <div className="max-w-5xl space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Provider Risk</h1>
        <p className="text-sm text-gray-500 mt-1">
          Per-provider explanation of the ML model's billing-variance score, including the top SHAP
          contributions and a plain-English summary. Helps explain "why is this provider on the radar?"
        </p>
      </div>

      {/* Band filter chips */}
      <div className="flex items-center gap-2 flex-wrap">
        {(['ALL', 'HIGH', 'MEDIUM', 'LOW'] as const).map((b) => {
          const active = bandFilter === b
          const count = b === 'ALL' ? items.length : items.filter((p) => p.band === b).length
          return (
            <button
              key={b}
              onClick={() => setBandFilter(b)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors ${
                active
                  ? (b === 'ALL'
                      ? 'bg-gray-900 text-white border-gray-900'
                      : `${BAND_COLOR[b]} ring-2 ring-offset-1 ring-current`)
                  : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
              }`}
            >
              {b === 'ALL' ? 'All' : b}
              <span className="text-[10px] opacity-70">({count})</span>
            </button>
          )
        })}
        {highCount > 0 && (
          <span className="text-xs text-gray-400 ml-auto">
            {highCount} provider{highCount === 1 ? '' : 's'} in HIGH risk band
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : error ? (
        <p className="text-sm text-red-600">Failed to load: {(error as any)?.response?.data?.detail ?? String(error)}</p>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-gray-400 italic px-4 py-12 text-center bg-white border border-gray-200 rounded-xl">
          No providers in this band.
        </p>
      ) : (
        <div className="space-y-3">
          {filtered.map((p) => {
            const isOpen = expanded === p.npi
            const pct = Math.round(p.score * 100)
            return (
              <div key={p.npi} className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                <button
                  onClick={() => setExpanded(isOpen ? null : p.npi)}
                  className="w-full text-left p-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="grid grid-cols-12 gap-3 items-center">
                    {/* Identity */}
                    <div className="col-span-5">
                      <div className="flex items-center gap-2">
                        {isOpen
                          ? <ChevronDown className="w-4 h-4 text-gray-400" />
                          : <ChevronRight className="w-4 h-4 text-gray-400" />}
                        <p className="text-sm font-bold text-gray-900">{p.name}</p>
                      </div>
                      <div className="text-xs text-gray-500 ml-6 mt-0.5">
                        <span className="font-mono">{p.npi}</span> · {p.specialty}
                      </div>
                    </div>

                    {/* Score bar */}
                    <div className="col-span-5">
                      <div className="flex items-center gap-2">
                        <div className="flex-1">
                          <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                            <div className={`h-2 rounded-full transition-all ${BAND_BAR[p.band]}`}
                                 style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                        <span className="text-sm font-bold text-gray-900 tabular-nums w-12 text-right">
                          {p.score.toFixed(2)}
                        </span>
                      </div>
                    </div>

                    {/* Band + claims */}
                    <div className="col-span-2 flex items-center justify-end gap-2">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${BAND_COLOR[p.band]}`}>
                        {p.band}
                      </span>
                      <span className="text-[11px] text-gray-400 inline-flex items-center gap-0.5">
                        <FileText className="w-3 h-3" /> {p.n_claims_in_system}
                      </span>
                    </div>
                  </div>
                </button>

                {isOpen && (
                  <div className="px-4 pb-4 border-t border-gray-100 bg-gray-50/50">
                    {/* Plain English */}
                    <div className="bg-white border border-gray-200 rounded-lg p-3 mt-3 mb-3">
                      <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1">
                        Plain language explanation
                      </p>
                      <p className="text-sm text-gray-800 leading-relaxed">{p.plain_english}</p>
                    </div>

                    {/* Top drivers table */}
                    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
                      <div className="px-3 py-2 border-b border-gray-100">
                        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                          Top SHAP contributors
                        </p>
                      </div>
                      <table className="min-w-full text-xs">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-3 py-1.5 text-left font-semibold text-gray-500">Feature</th>
                            <th className="px-3 py-1.5 text-right font-semibold text-gray-500">This provider</th>
                            <th className="px-3 py-1.5 text-right font-semibold text-gray-500">Typical</th>
                            <th className="px-3 py-1.5 text-right font-semibold text-gray-500">SHAP</th>
                            <th className="px-3 py-1.5 text-left font-semibold text-gray-500 w-24">Effect</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {p.top_drivers.map((d) => (
                            <tr key={d.feature}>
                              <td className="px-3 py-1.5 text-gray-800">{d.label}</td>
                              <td className="px-3 py-1.5 text-right font-mono text-gray-900 font-semibold">
                                {d.provider_value_fmt}
                              </td>
                              <td className="px-3 py-1.5 text-right font-mono text-gray-500">
                                {d.population_mean_fmt}
                              </td>
                              <td className={`px-3 py-1.5 text-right font-mono ${
                                d.shap_contribution > 0 ? 'text-red-600' :
                                d.shap_contribution < 0 ? 'text-green-600' : 'text-gray-500'
                              }`}>
                                {d.shap_contribution >= 0 ? '+' : ''}{d.shap_contribution.toFixed(3)}
                              </td>
                              <td className="px-3 py-1.5">
                                {d.direction === 'raises' ? (
                                  <span className="inline-flex items-center gap-1 text-red-600 text-[11px] font-semibold">
                                    <TrendingUp className="w-3 h-3" /> raises score
                                  </span>
                                ) : d.direction === 'lowers' ? (
                                  <span className="inline-flex items-center gap-1 text-green-600 text-[11px] font-semibold">
                                    <TrendingDown className="w-3 h-3" /> lowers score
                                  </span>
                                ) : (
                                  <span className="text-gray-400 text-[11px]">neutral</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <p className="text-[11px] text-gray-400 mt-3">
                      SHAP values decompose the model's exact output into per-feature contributions.
                      Positive values raise the risk score; negative values lower it.
                      "Typical" is the population mean across all providers in the training data.
                    </p>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
