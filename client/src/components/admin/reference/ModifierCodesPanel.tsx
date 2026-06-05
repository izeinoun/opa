import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Lock, AlertTriangle } from 'lucide-react'
import api from '../../../services/api'
import type { ModifierCode } from '../../../types'
import { MasterDetail, ConfidenceGauge, CertaintyBadge, ProvenanceBlock, EditableText } from './shared'

function RiskBar({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color = score >= 0.6 ? 'bg-red-400' : score >= 0.4 ? 'bg-amber-400' : 'bg-green-400'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-600 font-mono w-8 text-right">{pct}%</span>
    </div>
  )
}

function ModListItem({ mod, active, onClick }: { mod: ModifierCode; active: boolean; onClick: () => void }) {
  const riskColor = mod.audit_risk_score >= 0.6 ? 'text-red-600' : mod.audit_risk_score >= 0.4 ? 'text-amber-600' : 'text-green-600'
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2.5 hover:bg-gray-50 transition-colors
        ${active ? 'bg-[#FE017D]/5 border-r-2 border-[#FE017D]' : ''}`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={`font-mono text-sm font-bold ${active ? 'text-[#FE017D]' : 'text-gray-800'}`}>
            {mod.code}
          </span>
          {mod.ncci_override && (
            <span className="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-medium">NCCI</span>
          )}
        </div>
        <span className={`text-xs font-semibold ${riskColor}`}>
          {Math.round(mod.audit_risk_score * 100)}%
        </span>
      </div>
      <p className="text-xs text-gray-500 truncate mt-0.5">{mod.description}</p>
    </button>
  )
}

function ModDetail({ mod }: { mod: ModifierCode }) {
  const qc = useQueryClient()
  const saveMutation = useMutation({
    mutationFn: async (patch: Record<string, unknown>) =>
      (await api.patch<ModifierCode>(`/admin/modifier-codes/${mod.code}`, patch)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'modifier-codes'] }),
  })
  const save = (field: string, value: unknown) => saveMutation.mutate({ [field]: value })

  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-xl font-bold text-gray-900">{mod.code}</span>
              <span className="px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-600 capitalize">
                {mod.modifier_type}
              </span>
              <span className="px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-600 uppercase">
                {mod.applies_to}
              </span>
              {mod.ncci_override && (
                <span className="px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-700">
                  NCCI override
                </span>
              )}
              {mod.requires_documentation && (
                <span className="px-2 py-0.5 rounded text-xs font-semibold bg-purple-100 text-purple-700">
                  Doc required
                </span>
              )}
            </div>
            <p className="text-sm text-gray-600 mt-1">{mod.description}</p>
          </div>
          <Lock className="w-4 h-4 text-gray-300 flex-shrink-0 mt-1" />
        </div>
      </div>

      {/* Audit risk */}
      <div className="bg-gray-50 rounded-lg p-3 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs text-gray-600">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
            <span className="font-semibold">Audit risk score</span>
          </div>
          <span className={`text-sm font-bold ${
            mod.audit_risk_score >= 0.6 ? 'text-red-600' :
            mod.audit_risk_score >= 0.4 ? 'text-amber-600' : 'text-green-600'
          }`}>
            {Math.round(mod.audit_risk_score * 100)}%
          </span>
        </div>
        <RiskBar score={mod.audit_risk_score} />
      </div>

      {/* Payment impact */}
      {(mod.payment_impact || mod.payment_factor != null) && (
        <div className="flex items-center gap-4">
          {mod.payment_impact && (
            <div>
              <p className="text-[10px] text-gray-400 uppercase tracking-wider">Payment impact</p>
              <p className="text-sm font-semibold text-gray-800 capitalize">{mod.payment_impact.replace('_', ' ')}</p>
            </div>
          )}
          {mod.payment_factor != null && (
            <div>
              <p className="text-[10px] text-gray-400 uppercase tracking-wider">Factor</p>
              <p className="text-sm font-semibold text-gray-800">×{mod.payment_factor}</p>
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Data confidence</span>
          <ConfidenceGauge value={mod.data_confidence} />
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Rule certainty</span>
          <CertaintyBadge value={mod.rule_certainty} />
        </div>
      </div>

      <EditableText
        label="Audit notes (LLM context)"
        value={mod.audit_notes}
        placeholder="Describe when this modifier is appropriate, common misuse patterns, and what documentation to require…"
        rows={5}
        saving={saveMutation.isPending}
        onSave={val => save('audit_notes', val)}
      />

      <ProvenanceBlock
        authority={mod.source_authority}
        document={mod.source_document}
        reviewedAt={mod.last_reviewed_at}
      />
    </div>
  )
}

export default function ModifierCodesPanel() {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<'code' | 'risk'>('risk')

  const { data: mods = [], isLoading } = useQuery<ModifierCode[]>({
    queryKey: ['admin', 'modifier-codes'],
    queryFn: async () => (await api.get<ModifierCode[]>('/admin/modifier-codes')).data,
  })

  const filtered = mods
    .filter(m =>
      m.code.toLowerCase().includes(search.toLowerCase()) ||
      m.description.toLowerCase().includes(search.toLowerCase())
    )
    .sort((a, b) => sortBy === 'risk'
      ? b.audit_risk_score - a.audit_risk_score
      : a.code.localeCompare(b.code)
    )

  const selectedMod = mods.find(m => m.code === selected) ?? null

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 py-3 border-b border-gray-200 bg-white flex items-center gap-3">
        <h2 className="text-sm font-bold text-gray-900">Modifier Codes</h2>
        <span className="text-xs text-gray-400">{mods.length} modifiers</span>
      </div>

      {isLoading ? (
        <div className="flex-1 p-5 space-y-2 animate-pulse">
          {[...Array(6)].map((_, i) => <div key={i} className="h-11 bg-gray-100 rounded-lg" />)}
        </div>
      ) : (
        <div className="flex-1 min-h-0">
          <MasterDetail
            search={search}
            onSearch={setSearch}
            searchPlaceholder="Search modifiers…"
            listHeader={
              <div className="flex gap-1">
                {(['risk', 'code'] as const).map(s => (
                  <button key={s} onClick={() => setSortBy(s)}
                    className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                      sortBy === s ? 'bg-[#FE017D] text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    {s === 'risk' ? 'By risk' : 'By code'}
                  </button>
                ))}
              </div>
            }
            hasSelection={!!selectedMod}
            listItems={filtered.map(m => (
              <ModListItem key={m.code} mod={m} active={m.code === selected} onClick={() => setSelected(m.code)} />
            ))}
            detail={selectedMod ? <ModDetail mod={selectedMod} /> : null}
          />
        </div>
      )}
    </div>
  )
}
