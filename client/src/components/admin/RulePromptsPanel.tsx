import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Plus, Check, Star, Edit3 } from 'lucide-react'
import api from '../../services/api'

const KNOWN_RULES: { group: string; codes: string[] }[] = [
  { group: 'DET — Overpayment', codes: ['DET-01','DET-02','DET-04','DET-06','DET-08','DET-09','DET-10','DET-13','DET-16','DET-18','DET-19'] },
  { group: 'FWA — Fraud/Waste/Abuse', codes: ['FWA-02','FWA-03'] },
  { group: 'CHG — Charge', codes: ['CHG-002','CHG-003'] },
  { group: 'STR — Structural', codes: ['STR-003','STR-008','STR-009','STR-010','STR-012','STR-013','STR-014'] },
]

const LLM_MODELS = [
  { value: 'claude-opus-4-8',          label: 'Opus 4.8' },
  { value: 'claude-sonnet-4-6',         label: 'Sonnet 4.6' },
  { value: 'claude-haiku-4-5-20251001', label: 'Haiku 4.5' },
]

interface RulePrompt {
  id: string
  rule_id: string
  prompt_type: string
  version: number
  prompt_template: string
  output_schema: string | null
  active: boolean
  model: string
  temperature: number
  last_edited_by: string | null
  last_edited_at: string
  notes: string | null
  eval_score: number | null
}

const PROMPT_TYPE_STYLES: Record<string, string> = {
  evaluation:    'bg-blue-100 text-blue-700',
  verification:  'bg-amber-100 text-amber-700',
  explanation:   'bg-purple-100 text-purple-700',
}

export default function RulePromptsPanel() {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [creatingForRule, setCreatingForRule] = useState<string | undefined>(undefined)
  const [editing, setEditing] = useState<RulePrompt | null>(null)

  const { data: prompts = [], isLoading } = useQuery<RulePrompt[]>({
    queryKey: ['rule-prompts'],
    queryFn: async () => (await api.get('/rule-prompts')).data,
  })

  const activateMut = useMutation({
    mutationFn: (id: string) => api.post(`/rule-prompts/${id}/activate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rule-prompts'] }),
  })

  const patchMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { notes?: string; eval_score?: number } }) =>
      api.put(`/rule-prompts/${id}`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['rule-prompts'] }); setEditing(null) },
  })

  const createMut = useMutation({
    mutationFn: (body: object) => api.post('/rule-prompts', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rule-prompts'] })
      setCreating(false)
      setCreatingForRule(undefined)
    },
  })

  const existingRuleIds = [...new Set(prompts.map(p => p.rule_id))]

  // Group by rule_id, sort each group by prompt_type then version desc
  const byRule: Record<string, RulePrompt[]> = {}
  for (const p of prompts) {
    if (!byRule[p.rule_id]) byRule[p.rule_id] = []
    byRule[p.rule_id].push(p)
  }
  const PT_ORDER: Record<string, number> = { evaluation: 0, verification: 1, explanation: 2 }
  for (const k of Object.keys(byRule)) {
    byRule[k].sort((a, b) => {
      const ptDiff = (PT_ORDER[a.prompt_type] ?? 99) - (PT_ORDER[b.prompt_type] ?? 99)
      return ptDiff !== 0 ? ptDiff : b.version - a.version
    })
  }
  const ruleIds = Object.keys(byRule).sort()

  return (
    <div className="space-y-4 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500 mt-0.5">
            Versioned LLM prompts for detector rules. One version is active per rule at a time.
            Editing creates a new version — history is preserved.
          </p>
        </div>
        <button
          onClick={() => setCreating(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" /> New prompt
        </button>
      </div>

      {isLoading && <p className="text-sm text-gray-400">Loading…</p>}

      {ruleIds.map(ruleId => {
        const versions = byRule[ruleId]
        const active = versions.find(v => v.active)
        const isOpen = expanded === ruleId

        return (
          <div key={ruleId} className="border border-gray-200 rounded-xl overflow-hidden">
            {/* Rule header */}
            <button
              onClick={() => setExpanded(isOpen ? null : ruleId)}
              className="w-full flex items-center gap-3 px-4 py-3 bg-white hover:bg-gray-50 transition-colors text-left"
            >
              {isOpen
                ? <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />
                : <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />}
              <span className="font-mono font-bold text-sm text-gray-900">{ruleId}</span>
              {active && (
                <span className="ml-1 text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">
                  v{active.version} active
                </span>
              )}
              {/* Show distinct active prompt_types as badges */}
              {versions.filter(v => v.active).map(v => (
                <span key={v.prompt_type}
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${PROMPT_TYPE_STYLES[v.prompt_type] ?? 'bg-gray-100 text-gray-600'}`}>
                  {v.prompt_type}
                </span>
              ))}
              <span className="ml-auto text-xs text-gray-400">{versions.length} version{versions.length !== 1 ? 's' : ''}</span>
              {active && (
                <span className="text-xs text-gray-400 font-mono">{active.model}</span>
              )}
            </button>

            {/* Version list */}
            {isOpen && (
              <div className="border-t border-gray-100 divide-y divide-gray-100">
                {versions.map(v => (
                  <VersionRow
                    key={v.id}
                    prompt={v}
                    onActivate={() => activateMut.mutate(v.id)}
                    activating={activateMut.isPending}
                    onEdit={() => setEditing(v)}
                  />
                ))}
                <div className="px-4 py-2 bg-gray-50">
                  <button
                    onClick={() => { setCreatingForRule(ruleId); setCreating(true) }}
                    className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                  >
                    + New version for {ruleId}
                  </button>
                </div>
              </div>
            )}
          </div>
        )
      })}

      {prompts.length === 0 && !isLoading && (
        <p className="text-sm text-gray-400 italic">No rule prompts configured yet.</p>
      )}

      {/* Create modal */}
      {creating && (
        <CreatePromptModal
          onSave={(body) => createMut.mutate(body)}
          onClose={() => { setCreating(false); setCreatingForRule(undefined) }}
          saving={createMut.isPending}
          error={(createMut.error as any)?.response?.data?.detail}
          existingRuleIds={existingRuleIds}
          defaultRuleId={creatingForRule}
        />
      )}

      {/* Edit modal */}
      {editing && (
        <EditPromptModal
          prompt={editing}
          onSave={(body) => patchMut.mutate({ id: editing.id, body })}
          onClose={() => setEditing(null)}
          saving={patchMut.isPending}
        />
      )}
    </div>
  )
}

function VersionRow({ prompt, onActivate, activating, onEdit }: {
  prompt: RulePrompt
  onActivate: () => void
  activating: boolean
  onEdit: () => void
}) {
  const [showPrompt, setShowPrompt] = useState(false)

  return (
    <div className={`px-4 py-3 ${prompt.active ? 'bg-green-50/40' : 'bg-white'}`}>
      <div className="flex items-center gap-3">
        <span className="text-xs font-mono text-gray-500 w-6">v{prompt.version}</span>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${PROMPT_TYPE_STYLES[prompt.prompt_type] ?? 'bg-gray-100 text-gray-600'}`}>
          {prompt.prompt_type}
        </span>
        {prompt.active
          ? <span className="inline-flex items-center gap-1 text-xs text-green-700 font-semibold"><Check className="w-3 h-3" /> Active</span>
          : <button
              onClick={onActivate}
              disabled={activating}
              className="text-xs text-indigo-600 hover:text-indigo-800 font-medium disabled:opacity-50"
            >
              Activate
            </button>
        }
        <span className="text-xs text-gray-400 font-mono">{prompt.model}</span>
        <span className="text-xs text-gray-400">temp {prompt.temperature}</span>
        {prompt.eval_score != null && (
          <span className="inline-flex items-center gap-0.5 text-xs text-amber-600 font-medium">
            <Star className="w-3 h-3" /> {prompt.eval_score.toFixed(1)}
          </span>
        )}
        <span className="text-xs text-gray-400 ml-auto">
          {prompt.last_edited_by && `by ${prompt.last_edited_by} · `}
          {prompt.last_edited_at?.slice(0, 10)}
        </span>
        <button onClick={onEdit} className="text-gray-400 hover:text-gray-700">
          <Edit3 className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={() => setShowPrompt(v => !v)}
          className="text-xs text-gray-400 hover:text-gray-700 font-medium"
        >
          {showPrompt ? 'Hide' : 'View'}
        </button>
      </div>
      {prompt.notes && (
        <p className="text-xs text-gray-500 mt-1 ml-9">{prompt.notes}</p>
      )}
      {showPrompt && (
        <div className="mt-2 ml-9 space-y-2">
          <pre className="text-xs bg-gray-900 text-green-300 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto">
            {prompt.prompt_template}
          </pre>
          {prompt.output_schema && (
            <details className="text-xs">
              <summary className="text-gray-500 cursor-pointer hover:text-gray-700">Output schema</summary>
              <pre className="mt-1 bg-gray-50 border border-gray-200 rounded p-2 overflow-x-auto text-gray-700">
                {JSON.stringify(JSON.parse(prompt.output_schema), null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  )
}

function CreatePromptModal({ onSave, onClose, saving, error, existingRuleIds, defaultRuleId }: {
  onSave: (body: object) => void
  onClose: () => void
  saving: boolean
  error?: string
  existingRuleIds: string[]
  defaultRuleId?: string
}) {
  const [form, setForm] = useState({
    rule_id: defaultRuleId ?? '',
    prompt_type: 'evaluation',
    model: 'claude-sonnet-4-6',
    temperature: '0.0',
    prompt_template: '',
    output_schema: '',
    notes: '',
    activate: true,
  })
  const [customRuleId, setCustomRuleId] = useState(false)

  const set = (k: string, v: string | boolean) => setForm(f => ({ ...f, [k]: v }))

  // Available rules = known rules not yet in any prompt (unless we're adding a version to an existing rule)
  const availableRules = KNOWN_RULES.map(g => ({
    ...g,
    codes: g.codes.filter(c => !existingRuleIds.includes(c)),
  })).filter(g => g.codes.length > 0)

  const handleSave = () => {
    onSave({
      rule_id: form.rule_id.trim(),
      prompt_type: form.prompt_type,
      model: form.model,
      temperature: parseFloat(form.temperature) || 0,
      prompt_template: form.prompt_template,
      output_schema: form.output_schema.trim() || null,
      notes: form.notes.trim() || null,
      activate: form.activate,
    })
  }

  const isNewVersion = !!defaultRuleId

  return (
    <Modal title={isNewVersion ? `New version — ${defaultRuleId}` : 'New rule prompt'} onClose={onClose} wide>
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          {/* Rule ID — dropdown of unprompted rules, or locked when adding a new version */}
          <Field label="Rule">
            {isNewVersion ? (
              <div className={`${input} bg-gray-50 text-gray-700 font-mono font-semibold`}>{defaultRuleId}</div>
            ) : customRuleId ? (
              <div className="flex gap-1.5 items-center">
                <input value={form.rule_id} onChange={e => set('rule_id', e.target.value)}
                  className={input} placeholder="e.g. DET-20" autoFocus />
                <button type="button" onClick={() => { setCustomRuleId(false); set('rule_id', '') }}
                  className="text-xs text-gray-400 hover:text-gray-600 whitespace-nowrap">← list</button>
              </div>
            ) : (
              <div className="flex gap-1.5 items-center">
                <select value={form.rule_id} onChange={e => set('rule_id', e.target.value)}
                  className={input}>
                  <option value="">— select rule —</option>
                  {availableRules.map(g => (
                    <optgroup key={g.group} label={g.group}>
                      {g.codes.map(c => <option key={c} value={c}>{c}</option>)}
                    </optgroup>
                  ))}
                </select>
                <button type="button" onClick={() => setCustomRuleId(true)}
                  className="text-xs text-gray-400 hover:text-gray-600 whitespace-nowrap">other…</button>
              </div>
            )}
          </Field>
          <Field label="Prompt type">
            <select value={form.prompt_type} onChange={e => set('prompt_type', e.target.value)}
              className={input}>
              <option value="evaluation">evaluation</option>
              <option value="verification">verification</option>
              <option value="explanation">explanation</option>
            </select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Model">
            <select value={form.model} onChange={e => set('model', e.target.value)}
              className={input}>
              {LLM_MODELS.map(m => (
                <option key={m.value} value={m.value}>{m.label} — {m.value}</option>
              ))}
            </select>
          </Field>
          <Field label="Temperature">
            <input type="number" min="0" max="1" step="0.1"
              value={form.temperature} onChange={e => set('temperature', e.target.value)}
              className={input} />
          </Field>
        </div>
        <Field label="Prompt template">
          <textarea value={form.prompt_template} onChange={e => set('prompt_template', e.target.value)}
            rows={18} className={`${input} font-mono text-xs leading-relaxed`}
            placeholder="You are a healthcare claims auditor…&#10;&#10;## Claim&#10;{{claim_lines}}&#10;&#10;## Task&#10;…" />
        </Field>
        <Field label="Output schema (JSON, optional)">
          <textarea value={form.output_schema} onChange={e => set('output_schema', e.target.value)}
            rows={4} className={`${input} font-mono text-xs`}
            placeholder='{"type":"object","properties":{…}}' />
        </Field>
        <Field label="Notes">
          <input value={form.notes} onChange={e => set('notes', e.target.value)}
            className={input} placeholder="Why this version was created…" />
        </Field>
        <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
          <input type="checkbox" checked={form.activate}
            onChange={e => set('activate', e.target.checked)}
            className="rounded border-gray-300" />
          Activate immediately (deactivates current version)
        </label>
        {error && <p className="text-xs text-red-600">{error}</p>}
        <div className="flex gap-2 pt-1">
          <button onClick={onClose} className={secondaryBtn}>Cancel</button>
          <button onClick={handleSave} disabled={!form.rule_id || !form.prompt_template || saving}
            className={primaryBtn}>
            {saving ? 'Saving…' : 'Create'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

function EditPromptModal({ prompt, onSave, onClose, saving }: {
  prompt: RulePrompt
  onSave: (body: { notes?: string; eval_score?: number }) => void
  onClose: () => void
  saving: boolean
}) {
  const [notes, setNotes] = useState(prompt.notes ?? '')
  const [evalScore, setEvalScore] = useState(prompt.eval_score?.toString() ?? '')

  return (
    <Modal title={`Edit ${prompt.rule_id} v${prompt.version}`} onClose={onClose}>
      <div className="space-y-3">
        <Field label="Notes">
          <textarea value={notes} onChange={e => setNotes(e.target.value)}
            rows={3} className={input} />
        </Field>
        <Field label="Eval score (0–1, human-rated quality)">
          <input type="number" min="0" max="1" step="0.05"
            value={evalScore} onChange={e => setEvalScore(e.target.value)}
            className={`${input} w-32`} placeholder="0.85" />
        </Field>
        <div className="flex gap-2 pt-1">
          <button onClick={onClose} className={secondaryBtn}>Cancel</button>
          <button
            onClick={() => onSave({
              notes: notes.trim() || undefined,
              eval_score: evalScore ? parseFloat(evalScore) : undefined,
            })}
            disabled={saving}
            className={primaryBtn}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
         onClick={onClose}>
      <div className={`bg-white rounded-xl shadow-xl w-full p-5 max-h-[90vh] overflow-y-auto ${wide ? 'max-w-4xl' : 'max-w-2xl'}`}
           onClick={e => e.stopPropagation()}>
        <h3 className="text-base font-bold text-gray-900 mb-4">{title}</h3>
        {children}
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-gray-600 mb-1">{label}</label>
      {children}
    </div>
  )
}

const input = 'w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100'
const primaryBtn = 'flex-1 px-4 py-2 text-sm font-semibold bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:bg-gray-200 disabled:text-gray-400 transition-colors'
const secondaryBtn = 'px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50'
