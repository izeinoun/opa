import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Lock, Scale } from 'lucide-react'
import api from '../../../services/api'
import type { DRGCode } from '../../../types'
import { MasterDetail, ConfidenceGauge, CertaintyBadge, ProvenanceBlock, EditableText } from './shared'

function DrgListItem({ drg, active, onClick }: { drg: DRGCode; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2.5 hover:bg-gray-50 transition-colors
        ${active ? 'bg-[#FE017D]/5 border-r-2 border-[#FE017D]' : ''}`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className={`font-mono text-xs font-bold ${active ? 'text-[#FE017D]' : 'text-gray-700'}`}>
            {drg.code}
          </span>
          {drg.is_surgical && (
            <span className="text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-medium">Surg</span>
          )}
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {drg.weight != null && (
            <span className="text-[10px] text-gray-500 font-mono">{drg.weight.toFixed(4)}</span>
          )}
          <ConfidenceGauge value={drg.data_confidence} />
        </div>
      </div>
      <p className="text-xs text-gray-500 truncate mt-0.5">{drg.description}</p>
      {drg.mdc_description && (
        <p className="text-[10px] text-gray-400 truncate mt-0.5 italic">MDC {drg.mdc}: {drg.mdc_description}</p>
      )}
    </button>
  )
}

function DrgDetail({ drg }: { drg: DRGCode }) {
  const qc = useQueryClient()
  const saveMutation = useMutation({
    mutationFn: async (patch: Record<string, unknown>) =>
      (await api.patch<DRGCode>(`/admin/drg-codes/${drg.code}`, patch)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'drg-codes'] }),
  })
  const save = (field: string, value: unknown) => saveMutation.mutate({ [field]: value })

  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-xl font-bold text-gray-900">DRG {drg.code}</span>
              <span className="px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-600 uppercase">
                {drg.drg_type.replace('_', '-')}
              </span>
              {drg.is_surgical && (
                <span className="px-2 py-0.5 rounded text-xs font-semibold bg-blue-100 text-blue-700">
                  Surgical
                </span>
              )}
              {drg.effective_fy && (
                <span className="px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-500">
                  FY{drg.effective_fy}
                </span>
              )}
            </div>
            <p className="text-sm text-gray-600 mt-1">{drg.description}</p>
            {drg.mdc_description && (
              <p className="text-xs text-gray-400 italic mt-0.5">MDC {drg.mdc}: {drg.mdc_description}</p>
            )}
          </div>
          <Lock className="w-4 h-4 text-gray-300 flex-shrink-0 mt-1" />
        </div>
      </div>

      {/* Payment metrics */}
      <div className="grid grid-cols-3 gap-3">
        {[
          ['Relative Weight', drg.weight?.toFixed(4) ?? '—'],
          ['Geo Mean LOS', drg.geometric_mean_los != null ? `${drg.geometric_mean_los} days` : '—'],
          ['Arith Mean LOS', drg.arithmetic_mean_los != null ? `${drg.arithmetic_mean_los} days` : '—'],
        ].map(([label, val]) => (
          <div key={label as string} className="bg-gray-50 rounded-lg p-3 text-center">
            <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-1">{label}</p>
            <p className="text-sm font-bold text-gray-900">{val}</p>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Confidence</span>
          <ConfidenceGauge value={drg.data_confidence} />
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Certainty</span>
          <CertaintyBadge value={drg.rule_certainty} />
        </div>
      </div>

      {/* Triplet links */}
      {(drg.mcc_drg || drg.base_drg) && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-500">Triplet:</span>
          {drg.mcc_drg && drg.mcc_drg !== drg.code && (
            <span className="px-2 py-0.5 rounded text-xs font-semibold bg-red-50 text-red-700 border border-red-200"
              title="With MCC">
              DRG {drg.mcc_drg} w/MCC
            </span>
          )}
          {drg.mcc_drg === drg.code && (
            <span className="px-2 py-0.5 rounded text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
              This is the MCC tier
            </span>
          )}
          {drg.base_drg && drg.base_drg !== drg.code && (
            <span className="px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-600"
              title="Base tier (no CC/MCC)">
              DRG {drg.base_drg} base
            </span>
          )}
        </div>
      )}

      {/* Typical principal DX codes */}
      {drg.typical_principal_dx && (() => {
        try {
          const codes: string[] = JSON.parse(drg.typical_principal_dx)
          if (!codes.length) return null
          return (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1.5">
                Typical principal DX
              </p>
              <div className="flex flex-wrap gap-1">
                {codes.map(c => (
                  <span key={c} className="font-mono text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded border border-indigo-100">
                    {c}
                  </span>
                ))}
              </div>
            </div>
          )
        } catch { return null }
      })()}

      {/* Clinical criteria — the primary LLM field for DRGs */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <Scale className="w-3.5 h-3.5 text-gray-400" />
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Clinical criteria (LLM grouper context)
          </span>
        </div>
        <EditableText
          label=""
          value={drg.clinical_criteria}
          placeholder="Describe the diagnosis, procedure, and documentation requirements for this DRG. This text is passed to the LLM to reason about DRG validity…"
          rows={8}
          saving={saveMutation.isPending}
          onSave={val => save('clinical_criteria', val)}
        />
      </div>

      {drg.audit_notes && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-900">
          <p className="font-semibold mb-1">Audit guidance</p>
          <p className="leading-relaxed">{drg.audit_notes}</p>
        </div>
      )}

      <ProvenanceBlock
        authority={drg.source_authority}
        document={drg.source_document}
        reviewedAt={drg.last_reviewed_at}
      />
    </div>
  )
}

export default function DrgCodesPanel() {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<string | null>(null)

  const { data: drgs = [], isLoading } = useQuery<DRGCode[]>({
    queryKey: ['admin', 'drg-codes'],
    queryFn: async () => (await api.get<DRGCode[]>('/admin/drg-codes')).data,
  })

  const filtered = drgs.filter(d =>
    d.code.includes(search) ||
    d.description.toLowerCase().includes(search.toLowerCase()) ||
    (d.mdc_description ?? '').toLowerCase().includes(search.toLowerCase())
  )

  const selectedDrg = drgs.find(d => d.code === selected) ?? null

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 py-3 border-b border-gray-200 bg-white flex items-center gap-3">
        <h2 className="text-sm font-bold text-gray-900">DRG Codes</h2>
        <span className="text-xs text-gray-400">{drgs.length} codes</span>
      </div>

      {isLoading ? (
        <div className="flex-1 p-5 space-y-2 animate-pulse">
          {[...Array(5)].map((_, i) => <div key={i} className="h-14 bg-gray-100 rounded-lg" />)}
        </div>
      ) : (
        <div className="flex-1 min-h-0">
          <MasterDetail
            search={search}
            onSearch={setSearch}
            searchPlaceholder="Search DRG codes…"
            hasSelection={!!selectedDrg}
            listItems={filtered.map(d => (
              <DrgListItem key={d.code} drg={d} active={d.code === selected} onClick={() => setSelected(d.code)} />
            ))}
            detail={selectedDrg ? <DrgDetail drg={selectedDrg} /> : null}
          />
        </div>
      )}
    </div>
  )
}
