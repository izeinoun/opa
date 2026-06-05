import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, ListChecks } from 'lucide-react'
import api from '../../../services/api'
import { formatDate } from '../../../utils/dateUtils'

interface DetectorRule {
  rule_code: string; name: string; description: string
  enabled_prepay: boolean; enabled_postpay: boolean
  score: number; updated_at: string; has_implementation: boolean
  layer: string | null; layer_order: number | null; applies_to: string | null
  prepay: boolean; postpay: boolean; rationale: string | null
}

const PipelineToggle = ({
  isStub, capable, checked, onToggle, pending,
}: { isStub: boolean; capable: boolean; checked: boolean; onToggle: () => void; pending: boolean }) => {
  if (isStub || !capable) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <span className="relative inline-flex h-5 w-9 items-center rounded-full bg-gray-100 cursor-not-allowed">
          <span className="inline-block h-4 w-4 translate-x-0.5 rounded-full bg-white shadow" />
        </span>
        <span className="text-xs text-gray-300">{isStub ? '—' : 'N/A'}</span>
      </span>
    )
  }
  return (
    <button onClick={onToggle} disabled={pending} role="switch" aria-checked={checked}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${checked ? 'bg-[#FE017D]' : 'bg-gray-300'}`}>
      <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-4' : 'translate-x-0.5'}`} />
    </button>
  )
}

export default function DetectorRulesPanel() {
  const qc = useQueryClient()
  const [view, setView] = useState<'active' | 'catalog'>('active')
  const [savedRule, setSavedRule] = useState<string | null>(null)
  const [scoreDraft, setScoreDraft] = useState<Record<string, string>>({})

  const { data: rules = [], isLoading } = useQuery<DetectorRule[]>({
    queryKey: ['admin', 'detector-rules'],
    queryFn: async () => (await api.get<DetectorRule[]>('/admin/detector-rules')).data,
  })

  const updateMutation = useMutation({
    mutationFn: async ({ code, body }: { code: string; body: Partial<DetectorRule> }) =>
      (await api.put<DetectorRule>(`/admin/detector-rules/${code}`, body)).data,
    onSuccess: data => {
      qc.invalidateQueries({ queryKey: ['admin', 'detector-rules'] })
      setSavedRule(data.rule_code)
      setTimeout(() => setSavedRule(s => s === data.rule_code ? null : s), 1500)
    },
  })

  const activeRules  = rules.filter(r => r.has_implementation)
  const catalogRules = rules.filter(r => !r.has_implementation)

  const RuleTable = ({ rows, showStubStyle }: { rows: DetectorRule[]; showStubStyle: boolean }) => {
    const layers = showStubStyle
      ? rows.reduce<{ label: string; items: DetectorRule[] }[]>((acc, r) => {
          const label = r.layer ?? 'Uncategorized'
          const g = acc.find(a => a.label === label)
          if (g) g.items.push(r); else acc.push({ label, items: [r] })
          return acc
        }, [])
      : [{ label: '', items: rows }]

    return (
      <table className="min-w-full divide-y divide-gray-100">
        <thead className="bg-gray-50">
          <tr>
            {['Code', 'Rule', 'Weight', 'Pre-pay', 'Post-pay', 'Last Updated', ''].map(h => (
              <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {layers.map(({ label, items }) => (
            <>
              {label && (
                <tr key={`layer-${label}`} className="bg-gray-50">
                  <td colSpan={7} className="px-5 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">{label}</td>
                </tr>
              )}
              {items.map(r => {
                const isStub = !r.has_implementation
                const fullyOff = !isStub && !r.enabled_prepay && !r.enabled_postpay
                const draftVal = scoreDraft[r.rule_code]
                const displayScore = draftVal !== undefined ? draftVal : r.score.toString()
                const commitScore = () => {
                  const parsed = parseFloat(displayScore)
                  setScoreDraft(d => { const n = { ...d }; delete n[r.rule_code]; return n })
                  if (!isNaN(parsed) && parsed >= 0 && parsed <= 1 && parsed !== r.score)
                    updateMutation.mutate({ code: r.rule_code, body: { score: parsed } })
                }
                return (
                  <tr key={r.rule_code} className={fullyOff ? 'opacity-50 bg-white' : 'bg-white'}>
                    <td className={`px-5 py-3.5 text-sm font-mono font-semibold ${isStub ? 'text-gray-400' : 'text-gray-900'}`}>{r.rule_code}</td>
                    <td className="px-5 py-3.5 max-w-md">
                      <p className={`text-sm font-medium ${isStub ? 'text-gray-400' : 'text-gray-900'}`}>{r.name}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{r.description}</p>
                    </td>
                    <td className="px-5 py-3.5">
                      <input type="number" step="0.1" min="0" max="1"
                        value={displayScore} disabled={isStub}
                        onChange={e => setScoreDraft(d => ({ ...d, [r.rule_code]: e.target.value }))}
                        onBlur={commitScore}
                        onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
                        className={`w-20 px-2 py-1.5 border rounded-lg text-sm font-mono focus:outline-none
                          ${isStub ? 'bg-gray-50 border-gray-100 text-gray-400 cursor-not-allowed'
                            : 'bg-white border-gray-200 focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]'}`}
                      />
                    </td>
                    <td className="px-5 py-3.5">
                      <PipelineToggle isStub={isStub} capable={r.prepay} checked={r.enabled_prepay} pending={updateMutation.isPending}
                        onToggle={() => updateMutation.mutate({ code: r.rule_code, body: { enabled_prepay: !r.enabled_prepay } })} />
                    </td>
                    <td className="px-5 py-3.5">
                      <PipelineToggle isStub={isStub} capable={r.postpay} checked={r.enabled_postpay} pending={updateMutation.isPending}
                        onToggle={() => updateMutation.mutate({ code: r.rule_code, body: { enabled_postpay: !r.enabled_postpay } })} />
                    </td>
                    <td className="px-5 py-3.5 text-xs text-gray-400">{isStub ? '—' : formatDate(r.updated_at)}</td>
                    <td className="px-5 py-3.5">
                      {savedRule === r.rule_code && (
                        <span className="inline-flex items-center gap-1 text-xs text-green-700">
                          <CheckCircle className="w-3.5 h-3.5" /> Saved
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </>
          ))}
        </tbody>
      </table>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1 w-fit">
        {(['active', 'catalog'] as const).map(v => (
          <button key={v} onClick={() => setView(v)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              view === v ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {v === 'active' ? 'Active rules' : 'Rule catalog'}
            <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full font-semibold ${
              view === v ? 'bg-[#FE017D]/10 text-[#FE017D]' : 'bg-gray-200 text-gray-500'
            }`}>
              {v === 'active'
                ? activeRules.filter(r => r.enabled_prepay || r.enabled_postpay).length
                : catalogRules.length}
            </span>
          </button>
        ))}
      </div>

      <div className={`rounded-xl border p-4 text-sm flex items-start gap-2 ${
        view === 'active' ? 'bg-blue-50 border-blue-200 text-blue-900' : 'bg-amber-50 border-amber-200 text-amber-900'
      }`}>
        <ListChecks className="w-4 h-4 flex-shrink-0 mt-0.5" />
        <p className="text-xs">
          {view === 'active'
            ? 'Toggle Pre-pay and Post-pay independently. Greyed toggles indicate structural ineligibility. Weight is a confidence multiplier in the posterior update.'
            : 'Rules defined in the catalog without a live handler. Grouped by edit layer. Configurable once a handler is registered.'}
        </p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {isLoading
          ? <div className="p-5 space-y-2 animate-pulse">{[...Array(6)].map((_, i) => <div key={i} className="h-14 bg-gray-100 rounded-lg" />)}</div>
          : view === 'active' ? <RuleTable rows={activeRules} showStubStyle={false} />
            : <RuleTable rows={catalogRules} showStubStyle />
        }
      </div>
    </div>
  )
}
