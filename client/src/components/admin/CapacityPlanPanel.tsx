import { Fragment, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Sparkles, FlaskConical, AlertTriangle } from 'lucide-react'
import api from '../../services/api'
import EvCurveChart from './EvCurveChart'

// ── Types ────────────────────────────────────────────────────────────────────

interface CapacityRow {
  rank: number
  case_id: string
  case_number: string
  provider: string
  amount_at_risk: number
  probability: number
  ev: number
  within_capacity: boolean
}

interface CapacityPreview {
  probability_cutoff: number
  capacity: number
  total_open_cases: number
  gate_passed: number
  gate_excluded: number
  within_capacity_count: number
  backlog_count: number
  total_ev: number
  captured_ev: number
  backlog_ev: number
  capture_ratio: number
  ev_cut_line: number | null
  ev_curve: { n: number; capture_ratio: number }[]
  rows: CapacityRow[]
}

const card2 = 'bg-white rounded-xl border border-gray-200 shadow-sm p-5'
const labelCls = 'block text-xs font-medium text-gray-600 mb-1'
const inputCls = 'w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]'

const fmtInt = (v: number | null | undefined) => (v == null ? '—' : v.toLocaleString())
const fmtMoney = (v: number | null | undefined) => (v == null ? '—' : `$${Math.round(v).toLocaleString()}`)

// ── Component ─────────────────────────────────────────────────────────────────

export default function CapacityPlanPanel() {
  const [preview, setPreview] = useState<CapacityPreview | null>(null)
  const [gatePct, setGatePct] = useState(4) // secondary probability gate, %
  const [mode, setMode] = useState<'capacity' | 'capture'>('capacity')
  const [capacityInput, setCapacityInput] = useState<number | null>(null)
  const [capturePct, setCapturePct] = useState(90) // target % of EV to capture

  // Default team capacity is seeded from the saved config; the operational knobs
  // (capacity ↔ capture ratio) live here, not in the model hyperparameters.
  const { data: config } = useQuery<{ team_audit_capacity: number }>({
    queryKey: ['admin', 'training-config'],
    queryFn: async () => (await api.get('/admin/training-config')).data,
  })
  const capacity = capacityInput ?? config?.team_audit_capacity ?? 50

  const previewMutation = useMutation({
    mutationFn: async (params: Record<string, number>) =>
      (await api.get<CapacityPreview>('/admin/model/capacity-preview', { params })).data,
    onSuccess: (data) => setPreview(data),
  })
  const runPreview = () => {
    const params: Record<string, number> = {
      probability_cutoff: Math.min(Math.max(gatePct, 0), 100) / 100,
      backlog_preview: 25,
    }
    if (mode === 'capacity') params.capacity = capacity
    else params.target_capture = Math.min(Math.max(capturePct, 0), 100) / 100
    previewMutation.mutate(params)
  }

  return (
    <div className={card2}>
      <div className="flex items-center gap-2 mb-1 flex-wrap">
        <Sparkles className="w-4 h-4 text-[#FE017D]" />
        <h3 className="text-sm font-bold text-gray-900">Audit plan — expected value your team can capture</h3>
      </div>
      <p className="text-[11px] text-gray-400 mb-3">
        Cases are ranked by <span className="font-semibold">expected value ($ × probability)</span>, high to low.
        Drive the cut two equivalent ways: set your <span className="font-semibold">team capacity</span> and see the
        EV you capture, or set a <span className="font-semibold">capture target</span> and see the capacity it needs.
        Probability is a secondary gate (and shown per case). Then the rules run on what's worked.
      </p>

      {/* Mode toggle: which knob drives the cut */}
      <div className="inline-flex rounded-lg border border-gray-200 p-0.5 mb-3 text-xs font-semibold">
        <button onClick={() => setMode('capacity')}
          className={`px-3 py-1.5 rounded-md transition-colors ${mode === 'capacity' ? 'bg-[#FE017D] text-white' : 'text-gray-500 hover:text-gray-700'}`}>
          Set capacity → get capture %
        </button>
        <button onClick={() => setMode('capture')}
          className={`px-3 py-1.5 rounded-md transition-colors ${mode === 'capture' ? 'bg-[#FE017D] text-white' : 'text-gray-500 hover:text-gray-700'}`}>
          Set capture % → get capacity
        </button>
      </div>

      <div className="flex items-end gap-3 flex-wrap">
        {mode === 'capacity' ? (
          <div>
            <label className={labelCls}>Team capacity (cases/mo)</label>
            <input type="number" min={1} step={1} className={`${inputCls} w-28`}
              value={capacity}
              onChange={(e) => setCapacityInput(e.target.value === '' ? 1 : Number(e.target.value))} />
          </div>
        ) : (
          <div>
            <label className={labelCls}>EV capture target</label>
            <div className="flex items-center gap-2">
              <input type="number" min={1} max={100} step={1} className={`${inputCls} w-24`}
                value={capturePct}
                onChange={(e) => setCapturePct(e.target.value === '' ? 1 : Number(e.target.value))} />
              <span className="text-sm text-gray-500">% of EV</span>
            </div>
          </div>
        )}
        <div>
          <label className={labelCls}>Threshold <span className="text-gray-400 font-normal">(secondary)</span></label>
          <div className="flex items-center gap-2">
            <input type="number" min={0} max={100} step={1} className={`${inputCls} w-20`}
              value={gatePct}
              onChange={(e) => setGatePct(e.target.value === '' ? 0 : Number(e.target.value))} />
            <span className="text-sm text-gray-500">% prob.</span>
          </div>
        </div>
        <button
          onClick={runPreview}
          disabled={previewMutation.isPending}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-lg
                     border border-[#FE017D] text-[#FE017D] hover:bg-[#FE017D]/5 disabled:opacity-40 transition-colors">
          <FlaskConical className={`w-3.5 h-3.5 ${previewMutation.isPending ? 'animate-pulse' : ''}`} />
          {previewMutation.isPending ? 'Ranking…' : preview ? 'Refresh' : 'Build audit plan'}
        </button>
      </div>

      {preview && (
        <>
          {/* Headline: the two knobs, one derived from the other. */}
          <div className="flex items-stretch gap-3 mt-4 flex-wrap">
            <div className="flex-1 min-w-[150px] bg-[#FE017D]/5 border border-[#FE017D]/20 rounded-lg px-4 py-3">
              <div className="text-[11px] text-gray-500 uppercase tracking-wider">Capacity{mode === 'capture' ? ' needed' : ''}</div>
              <div className="text-2xl font-bold text-gray-900">{fmtInt(preview.within_capacity_count)} <span className="text-sm font-normal text-gray-400">cases</span></div>
            </div>
            <div className="flex items-center text-gray-300 font-bold text-lg">↔</div>
            <div className="flex-1 min-w-[150px] bg-[#FE017D]/5 border border-[#FE017D]/20 rounded-lg px-4 py-3">
              <div className="text-[11px] text-gray-500 uppercase tracking-wider">EV captured</div>
              <div className="text-2xl font-bold text-gray-900">{(preview.capture_ratio * 100).toFixed(1)}%</div>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
            <div className="bg-gray-50 rounded-lg px-3 py-2">
              <div className="text-[11px] text-gray-400">$ captured</div>
              <div className="text-sm font-bold text-gray-900">
                {fmtMoney(preview.captured_ev)} <span className="font-normal text-gray-400">/ {fmtMoney(preview.total_ev)}</span>
              </div>
            </div>
            <div className="bg-gray-50 rounded-lg px-3 py-2">
              <div className="text-[11px] text-gray-400">$ left on the table</div>
              <div className="text-sm font-bold text-gray-900">
                {fmtMoney(preview.backlog_ev)} <span className="font-normal text-gray-400">· {fmtInt(preview.backlog_count)} cases</span>
              </div>
            </div>
            <div className="bg-gray-50 rounded-lg px-3 py-2">
              <div className="text-[11px] text-gray-400">EV cut line</div>
              <div className="text-sm font-bold text-gray-900">{fmtMoney(preview.ev_cut_line)}</div>
            </div>
            <div className="bg-gray-50 rounded-lg px-3 py-2">
              <div className="text-[11px] text-gray-400">Gate</div>
              <div className="text-sm font-bold text-gray-900">
                {fmtInt(preview.gate_passed)} <span className="font-normal text-gray-400">of {fmtInt(preview.total_open_cases)} · {fmtInt(preview.gate_excluded)} excl.</span>
              </div>
            </div>
          </div>

          {/* Cumulative-EV curve — shows how concentrated the recoverable value is. */}
          {preview.ev_curve.length > 1 && (
            <div className="mt-4 rounded-lg border border-gray-100 p-3">
              <div className="text-[11px] text-gray-500 font-semibold mb-1">EV captured vs. cases worked</div>
              <EvCurveChart
                points={preview.ev_curve}
                maxN={preview.gate_passed}
                cutN={preview.within_capacity_count}
                captureRatio={preview.capture_ratio}
              />
              <p className="text-[11px] text-gray-400 mt-1">
                Steep early, flat late — the first cases carry most of the dollars, so pushing capacity past the knee adds little. Hover to read any point.
              </p>
            </div>
          )}

          <div className="overflow-auto mt-3 h-[420px] rounded-lg border border-gray-100">
            <table className="min-w-full text-sm">
              <thead className="sticky top-0 z-10 bg-white">
                <tr className="text-left text-[11px] text-gray-400 uppercase tracking-wider border-b border-gray-200">
                  <th className="py-2 px-3">#</th>
                  <th className="py-2 pr-3">Case</th>
                  <th className="py-2 pr-3">Provider</th>
                  <th className="py-2 pr-3 text-right">Amount</th>
                  <th className="py-2 pr-3 text-right">Probability</th>
                  <th className="py-2 pr-3 text-right">Expected value</th>
                  <th className="py-2 pr-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {preview.rows.map((r, i) => {
                  const firstBacklog = !r.within_capacity && (i === 0 || preview.rows[i - 1].within_capacity)
                  return (
                    <Fragment key={r.case_id}>
                      {firstBacklog && (
                        <tr>
                          <td colSpan={7} className="bg-amber-50 border-y border-amber-200 px-3 py-1 text-[11px] font-semibold text-amber-700">
                            ▼ cut at {fmtInt(preview.within_capacity_count)} cases — capturing {(preview.capture_ratio * 100).toFixed(1)}% of EV · {fmtInt(preview.backlog_count)} case{preview.backlog_count === 1 ? '' : 's'} ({fmtMoney(preview.backlog_ev)}) left on the table
                          </td>
                        </tr>
                      )}
                      <tr className={r.within_capacity ? '' : 'opacity-50'}>
                        <td className="py-2 px-3 font-mono text-gray-500">{r.rank}</td>
                        <td className="py-2 pr-3 font-mono text-xs text-gray-600">{r.case_number}</td>
                        <td className="py-2 pr-3 text-gray-700 text-xs">{r.provider}</td>
                        <td className="py-2 pr-3 text-right font-semibold text-gray-900">{fmtMoney(r.amount_at_risk)}</td>
                        <td className="py-2 pr-3 text-right text-gray-600">{(r.probability * 100).toFixed(1)}%</td>
                        <td className="py-2 pr-3 text-right font-semibold text-gray-900">{fmtMoney(r.ev)}</td>
                        <td className="py-2 pr-3 whitespace-nowrap">
                          {!r.within_capacity && (
                            <span className="inline-block px-2 py-0.5 rounded-full text-[11px] font-medium bg-gray-100 text-gray-500">backlog</span>
                          )}
                        </td>
                      </tr>
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-gray-400 mt-2">
            Showing {fmtInt(preview.rows.length)} of the {fmtInt(preview.gate_passed)} cases that clear the {(preview.probability_cutoff * 100).toFixed(0)}% probability gate, ranked by expected value
            (scroll past the cut line for the backlog). EV is concentrated, so a small capacity often captures most of the recoverable dollars.
          </p>
        </>
      )}
      {previewMutation.error && (
        <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5 mt-3">
          <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-red-700">
            {(previewMutation.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? (previewMutation.error as Error)?.message ?? 'Preview failed.'}
          </p>
        </div>
      )}
    </div>
  )
}
