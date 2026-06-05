import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Lock } from 'lucide-react'
import api from '../../../services/api'
import type { ICDCodeFull } from '../../../types'
import { MasterDetail, ConfidenceGauge, CertaintyBadge, ProvenanceBlock, EditableText } from './shared'

function IcdListItem({ code, active, onClick }: { code: ICDCodeFull; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2.5 hover:bg-gray-50 transition-colors
        ${active ? 'bg-[#FE017D]/5 border-r-2 border-[#FE017D]' : ''}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={`font-mono text-xs font-bold ${active ? 'text-[#FE017D]' : 'text-gray-700'}`}>
          {code.code}
        </span>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <ConfidenceGauge value={code.data_confidence} />
          {code.is_manifestation && (
            <span className="text-[10px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded font-medium">M</span>
          )}
        </div>
      </div>
      <p className="text-xs text-gray-500 truncate mt-0.5">{code.description}</p>
      {code.chapter && <p className="text-[10px] text-gray-400 truncate mt-0.5 italic">{code.chapter}</p>}
    </button>
  )
}

function IcdDetail({ code }: { code: ICDCodeFull }) {
  const qc = useQueryClient()
  const saveMutation = useMutation({
    mutationFn: async (patch: Record<string, unknown>) =>
      (await api.patch<ICDCodeFull>(`/admin/icd-codes/${code.code}`, patch)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'icd-codes'] }),
  })
  const save = (field: string, value: unknown) => saveMutation.mutate({ [field]: value })

  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-xl font-bold text-gray-900">{code.code}</span>
              <span className="px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-600 uppercase">
                {code.code_type === 'icd10_cm' ? 'ICD-10-CM' : 'ICD-10-PCS'}
              </span>
              {code.is_manifestation && (
                <span className="px-2 py-0.5 rounded text-xs font-semibold bg-purple-100 text-purple-700">
                  Manifestation
                </span>
              )}
              {code.is_etiology && (
                <span className="px-2 py-0.5 rounded text-xs font-semibold bg-indigo-100 text-indigo-700">
                  Etiology
                </span>
              )}
            </div>
            <p className="text-sm text-gray-600 mt-1">{code.description}</p>
            {code.chapter && <p className="text-xs text-gray-400 italic mt-0.5">{code.chapter}</p>}
          </div>
          <Lock className="w-4 h-4 text-gray-300 flex-shrink-0 mt-1" />
        </div>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Data confidence</span>
          <ConfidenceGauge value={code.data_confidence} />
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Rule certainty</span>
          <CertaintyBadge value={code.rule_certainty} />
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Setting</span>
          <span className={`px-2 py-0.5 rounded text-xs font-semibold capitalize ${
            code.typical_setting === 'inpatient'  ? 'bg-blue-100 text-blue-700' :
            code.typical_setting === 'outpatient' ? 'bg-green-100 text-green-700' :
            code.typical_setting === 'ed'         ? 'bg-orange-100 text-orange-700' :
                                                    'bg-gray-100 text-gray-600'
          }`}>
            {code.typical_setting}
          </span>
        </div>
        {code.typical_drg && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200"
            title="Typical inpatient DRG when this code is principal diagnosis">
            DRG {code.typical_drg}
          </span>
        )}
        {!code.valid_as_primary_dx && (
          <span className="px-2 py-0.5 rounded text-xs font-semibold bg-red-100 text-red-700 border border-red-200">
            Secondary DX only
          </span>
        )}
        {code.applicable_settings && (() => {
          try {
            const settings: string[] = JSON.parse(code.applicable_settings)
            return settings.length > 1 ? (
              <span className="text-xs text-gray-400" title={settings.join(', ')}>
                +{settings.length - 1} more settings
              </span>
            ) : null
          } catch { return null }
        })()}
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Category</span>
          <span className="text-xs text-gray-700 capitalize">{code.category}</span>
        </div>
      </div>

      <EditableText
        label="Audit notes (LLM context)"
        value={code.audit_notes}
        placeholder="Describe clinical context and what to verify when this diagnosis appears…"
        rows={5}
        saving={saveMutation.isPending}
        onSave={val => save('audit_notes', val)}
      />

      <ProvenanceBlock
        authority={code.source_authority}
        document={code.source_document}
        reviewedAt={code.last_reviewed_at}
      />
    </div>
  )
}

export default function IcdCodesPanel() {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'cm' | 'pcs'>('all')

  const { data: codes = [], isLoading } = useQuery<ICDCodeFull[]>({
    queryKey: ['admin', 'icd-codes'],
    queryFn: async () => (await api.get<ICDCodeFull[]>('/admin/icd-codes')).data,
  })

  const filtered = codes.filter(c => {
    if (filter === 'cm' && c.code_type !== 'icd10_cm') return false
    if (filter === 'pcs' && c.code_type !== 'icd10_pcs') return false
    return (
      c.code.toLowerCase().includes(search.toLowerCase()) ||
      c.description.toLowerCase().includes(search.toLowerCase()) ||
      (c.chapter ?? '').toLowerCase().includes(search.toLowerCase())
    )
  })

  const selectedCode = codes.find(c => c.code === selected) ?? null

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 py-3 border-b border-gray-200 bg-white flex items-center gap-3">
        <h2 className="text-sm font-bold text-gray-900">ICD-10 Codes</h2>
        <span className="text-xs text-gray-400">{codes.length} codes</span>
      </div>

      {isLoading ? (
        <div className="flex-1 p-5 space-y-2 animate-pulse">
          {[...Array(6)].map((_, i) => <div key={i} className="h-12 bg-gray-100 rounded-lg" />)}
        </div>
      ) : (
        <div className="flex-1 min-h-0">
          <MasterDetail
            search={search}
            onSearch={setSearch}
            searchPlaceholder="Search ICD codes…"
            listHeader={
              <div className="flex gap-1">
                {(['all', 'cm', 'pcs'] as const).map(f => (
                  <button key={f} onClick={() => setFilter(f)}
                    className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                      filter === f ? 'bg-[#FE017D] text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    {f === 'all' ? 'All' : f === 'cm' ? 'CM' : 'PCS'}
                  </button>
                ))}
              </div>
            }
            hasSelection={!!selectedCode}
            listItems={filtered.map(c => (
              <IcdListItem key={c.code} code={c} active={c.code === selected} onClick={() => setSelected(c.code)} />
            ))}
            detail={selectedCode ? <IcdDetail code={selectedCode} /> : null}
          />
        </div>
      )}
    </div>
  )
}
