import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Lock, Clock } from 'lucide-react'
import api from '../../../services/api'
import type { CPTCodeFull, CptDxCoverage, CptModifierMap } from '../../../types'
import {
  MasterDetail, ConfidenceGauge, CertaintyBadge, CoverageTypeBadge,
  ProvenanceBlock, EditableText,
} from './shared'

// ── List item ─────────────────────────────────────────────────────────────────

function CptListItem({ code, active, onClick }: { code: CPTCodeFull; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-2.5 hover:bg-gray-50 transition-colors
        ${active ? 'bg-[#FE017D]/5 border-r-2 border-[#FE017D]' : ''}`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className={`font-mono text-xs font-bold ${active ? 'text-[#FE017D]' : 'text-gray-700'}`}>
            {code.code}
          </span>
          {code.is_add_on && <span className="text-[10px] bg-purple-100 text-purple-700 px-1 rounded">+</span>}
          {code.global_period_days != null && code.global_period_days > 0 &&
            <span className="text-[10px] bg-amber-100 text-amber-700 px-1 rounded font-mono">{code.global_period_days}d</span>
          }
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <span className={`text-[10px] font-semibold ${code.risk_score >= 0.7 ? 'text-red-500' : code.risk_score >= 0.5 ? 'text-amber-500' : 'text-green-500'}`}>
            {Math.round(code.risk_score * 100)}%
          </span>
          <ConfidenceGauge value={code.data_confidence} />
        </div>
      </div>
      <p className="text-xs text-gray-500 truncate mt-0.5">{code.description}</p>
    </button>
  )
}

// ── DX Coverage sub-panel ─────────────────────────────────────────────────────

function DxCoveragePanel({ cptCode }: { cptCode: string }) {
  const qc = useQueryClient()
  const [addIcd, setAddIcd] = useState('')
  const [addType, setAddType] = useState('required')
  const [addRationale, setAddRationale] = useState('')

  const { data: rules = [] } = useQuery<CptDxCoverage[]>({
    queryKey: ['admin', 'cpt-dx-coverage', cptCode],
    queryFn: async () => (await api.get<CptDxCoverage[]>(`/admin/cpt-dx-coverage?cpt_code=${cptCode}`)).data,
  })

  const addMutation = useMutation({
    mutationFn: async () => api.post(`/admin/cpt-dx-coverage/${cptCode}`, {
      icd_code: addIcd.trim(), coverage_type: addType,
      rationale: addRationale.trim() || null, data_confidence: 0.75, rule_certainty: 'guideline',
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'cpt-dx-coverage', cptCode] })
      setAddIcd(''); setAddRationale('')
    },
  })

  const delMutation = useMutation({
    mutationFn: async (icd: string) => api.delete(`/admin/cpt-dx-coverage/${cptCode}/${icd}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'cpt-dx-coverage', cptCode] }),
  })

  const grouped = {
    required:   rules.filter(r => r.coverage_type === 'required'),
    supporting: rules.filter(r => r.coverage_type === 'supporting'),
    excluded:   rules.filter(r => r.coverage_type === 'excluded'),
  }

  return (
    <div className="space-y-3">
      {(['required', 'supporting', 'excluded'] as const).map(type => (
        grouped[type].length > 0 && (
          <div key={type}>
            <div className="flex items-center gap-2 mb-1.5">
              <CoverageTypeBadge value={type} />
              <span className="text-xs text-gray-400">({grouped[type].length})</span>
            </div>
            <div className="space-y-1">
              {grouped[type].map(r => (
                <div key={r.icd_code} className="flex items-start gap-2 group">
                  <div className="flex-1 bg-white border border-gray-100 rounded-lg px-3 py-1.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-semibold text-gray-700">{r.icd_code}</span>
                      <ConfidenceGauge value={r.data_confidence} />
                    </div>
                    {r.rationale && <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">{r.rationale}</p>}
                    {r.source_document && (
                      <p className="text-[11px] text-gray-400 mt-0.5">{r.source_document}</p>
                    )}
                  </div>
                  <button
                    onClick={() => delMutation.mutate(r.icd_code)}
                    disabled={delMutation.isPending}
                    className="opacity-0 group-hover:opacity-100 mt-1.5 p-1 text-red-400 hover:text-red-600 hover:bg-red-50 rounded transition-all"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )
      ))}

      {/* Add form */}
      <div className="border border-dashed border-gray-200 rounded-lg p-3 space-y-2">
        <p className="text-xs font-semibold text-gray-500">Add coverage rule</p>
        <div className="flex gap-2">
          <input
            value={addIcd} onChange={e => setAddIcd(e.target.value)}
            placeholder="ICD-10 code"
            className="flex-1 px-2 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D] font-mono"
          />
          <select
            value={addType} onChange={e => setAddType(e.target.value)}
            className="px-2 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none bg-white"
          >
            <option value="required">required</option>
            <option value="supporting">supporting</option>
            <option value="excluded">excluded</option>
          </select>
        </div>
        <input
          value={addRationale} onChange={e => setAddRationale(e.target.value)}
          placeholder="Rationale (optional)"
          className="w-full px-2 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]"
        />
        <button
          onClick={() => addMutation.mutate()}
          disabled={!addIcd.trim() || addMutation.isPending}
          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs bg-[#FE017D] text-white rounded-lg
                     hover:bg-[#e5006f] disabled:opacity-50 transition-colors"
        >
          <Plus className="w-3 h-3" /> Add rule
        </button>
      </div>
    </div>
  )
}

// ── Modifier map sub-panel ────────────────────────────────────────────────────

function ModifierMapPanel({ cptCode }: { cptCode: string }) {
  const qc = useQueryClient()
  const [addMod, setAddMod] = useState('')
  const [addNcci, setAddNcci] = useState(false)

  const { data: pairs = [] } = useQuery<CptModifierMap[]>({
    queryKey: ['admin', 'cpt-modifier-map', cptCode],
    queryFn: async () => (await api.get<CptModifierMap[]>(`/admin/cpt-modifier-map?cpt_code=${cptCode}`)).data,
  })

  const addMutation = useMutation({
    mutationFn: async () => api.post(`/admin/cpt-modifier-map/${cptCode}`, {
      modifier_code: addMod.trim(), ncci_override: addNcci,
      data_confidence: 0.85, rule_certainty: 'mandatory',
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'cpt-modifier-map', cptCode] })
      setAddMod(''); setAddNcci(false)
    },
  })

  const delMutation = useMutation({
    mutationFn: async (mod: string) => api.delete(`/admin/cpt-modifier-map/${cptCode}/${mod}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'cpt-modifier-map', cptCode] }),
  })

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {pairs.map(p => (
          <div key={p.modifier_code}
            className="group inline-flex items-center gap-1.5 px-2.5 py-1 bg-white border border-gray-200 rounded-full text-xs"
          >
            <span className="font-mono font-semibold text-gray-800">{p.modifier_code}</span>
            {p.ncci_override && <span className="text-[10px] text-amber-600 font-medium">NCCI</span>}
            {p.payment_factor != null && (
              <span className="text-[10px] text-gray-400">×{p.payment_factor}</span>
            )}
            <ConfidenceGauge value={p.data_confidence} />
            <button
              onClick={() => delMutation.mutate(p.modifier_code)}
              className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-600 transition-all"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </div>
        ))}
        {pairs.length === 0 && <p className="text-xs text-gray-400 italic">No modifiers mapped yet</p>}
      </div>

      <div className="flex items-center gap-2">
        <input
          value={addMod} onChange={e => setAddMod(e.target.value)}
          placeholder="Modifier code (e.g. 25)"
          className="w-32 px-2 py-1 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D] font-mono"
        />
        <label className="flex items-center gap-1 text-xs text-gray-600">
          <input type="checkbox" checked={addNcci} onChange={e => setAddNcci(e.target.checked)}
            className="rounded" />
          NCCI override
        </label>
        <button
          onClick={() => addMutation.mutate()}
          disabled={!addMod.trim() || addMutation.isPending}
          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-[#FE017D] text-white rounded-lg
                     hover:bg-[#e5006f] disabled:opacity-50 transition-colors"
        >
          <Plus className="w-3 h-3" /> Add
        </button>
      </div>
    </div>
  )
}

// ── Detail panel ──────────────────────────────────────────────────────────────

function CptDetail({ code }: { code: CPTCodeFull }) {
  const qc = useQueryClient()

  const saveMutation = useMutation({
    mutationFn: async (patch: Record<string, unknown>) =>
      (await api.patch<CPTCodeFull>(`/admin/cpt-codes/${code.code}`, patch)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'cpt-codes'] }),
  })

  const save = (field: string, value: unknown) => saveMutation.mutate({ [field]: value })

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-xl font-bold text-gray-900">{code.code}</span>
              <span className="px-2 py-0.5 rounded text-xs font-semibold bg-gray-100 text-gray-600 uppercase">
                {code.code_type}
              </span>
              {code.is_add_on && (
                <span className="px-2 py-0.5 rounded text-xs font-semibold bg-purple-100 text-purple-700">
                  Add-on
                </span>
              )}
              {code.global_period_days != null && code.global_period_days > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-amber-50 text-amber-700">
                  <Clock className="w-3 h-3" />{code.global_period_days}-day global
                </span>
              )}
            </div>
            <p className="text-sm text-gray-600 mt-1">{code.description}</p>
          </div>
          <span title="Code and description are read-only (CMS/AMA source)"><Lock className="w-4 h-4 text-gray-300 flex-shrink-0 mt-1" /></span>
        </div>
      </div>

      {/* Confidence + certainty */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Confidence</span>
          <ConfidenceGauge value={code.data_confidence} />
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Certainty</span>
          <CertaintyBadge value={code.rule_certainty} />
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Setting</span>
          <span className={`px-2 py-0.5 rounded text-xs font-semibold capitalize ${
            code.typical_setting === 'inpatient'   ? 'bg-blue-100 text-blue-700' :
            code.typical_setting === 'asc'         ? 'bg-purple-100 text-purple-700' :
            code.typical_setting === 'dme'         ? 'bg-orange-100 text-orange-700' :
            code.typical_setting.startsWith('sleep') ? 'bg-indigo-100 text-indigo-700' :
                                                       'bg-gray-100 text-gray-600'
          }`}>{code.typical_setting}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Audit risk</span>
          <span className={`text-xs font-semibold ${
            code.risk_score >= 0.7 ? 'text-red-600' :
            code.risk_score >= 0.5 ? 'text-amber-600' : 'text-green-600'
          }`}>{Math.round(code.risk_score * 100)}%</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Auth required</span>
          <span className={`text-xs font-medium ${code.cms_rac_flag ? 'text-[#FE017D]' : 'text-gray-400'}`}>
            {code.cms_rac_flag ? 'Yes' : 'No'}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">Specialty</span>
          <span className="text-xs text-gray-700">{code.specialty_typical}</span>
        </div>
      </div>

      {/* Audit notes — primary editable field */}
      <EditableText
        label="Audit notes (LLM context)"
        value={code.audit_notes}
        placeholder="Describe what to look for when auditing this CPT code…"
        rows={5}
        saving={saveMutation.isPending}
        onSave={val => save('audit_notes', val)}
      />

      {/* Provenance */}
      <ProvenanceBlock
        authority={code.source_authority}
        document={code.source_document}
        reviewedAt={code.last_reviewed_at}
      />

      {/* DX Coverage sub-panel */}
      <section>
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          DX Coverage Rules
        </h3>
        <DxCoveragePanel cptCode={code.code} />
      </section>

      {/* Modifier map sub-panel */}
      <section>
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          Valid Modifiers
        </h3>
        <ModifierMapPanel cptCode={code.code} />
      </section>
    </div>
  )
}

// ── Panel root ────────────────────────────────────────────────────────────────

export default function CptCodesPanel() {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<string | null>(null)

  const { data: codes = [], isLoading } = useQuery<CPTCodeFull[]>({
    queryKey: ['admin', 'cpt-codes'],
    queryFn: async () => (await api.get<CPTCodeFull[]>('/admin/cpt-codes')).data,
  })

  const filtered = codes.filter(c =>
    c.code.toLowerCase().includes(search.toLowerCase()) ||
    c.description.toLowerCase().includes(search.toLowerCase()) ||
    (c.specialty_typical ?? '').toLowerCase().includes(search.toLowerCase())
  )

  const selectedCode = codes.find(c => c.code === selected) ?? null

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 py-3 border-b border-gray-200 bg-white flex items-center gap-3">
        <h2 className="text-sm font-bold text-gray-900">CPT / HCPCS Codes</h2>
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
            searchPlaceholder="Search CPT codes…"
            hasSelection={!!selectedCode}
            listItems={filtered.map(c => (
              <CptListItem key={c.code} code={c} active={c.code === selected} onClick={() => setSelected(c.code)} />
            ))}
            detail={selectedCode ? <CptDetail code={selectedCode} /> : null}
          />
        </div>
      )}
    </div>
  )
}
