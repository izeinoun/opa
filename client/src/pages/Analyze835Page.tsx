import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { FileText, Zap, X, AlertTriangle, CheckCircle } from 'lucide-react'
import api from '../services/api'
import PriorityBadge from '../components/common/PriorityBadge'
import StatusBadge from '../components/common/StatusBadge'
import { formatCurrency } from '../utils/formatUtils'
import { detectorBadge } from '../utils/designSystem'
import type { CaseDetail } from '../types'

const SAMPLE_835 = `ISA*00*          *00*          *ZZ*PAYER123       *ZZ*PROVIDER456    *260101*1200*^*00501*000000001*0*P*:~
GS*HP*PAYER123*PROVIDER456*20260101*1200*1*X*005010X221A1~
ST*835*0001~
BPR*I*3200.00*C*CHK*CCP*01*021000021*DA*123456789*9876543210**01*021000021*DA*987654321*20260101~
TRN*1*ERA20260101001*9876543210~
DTM*405*20260101~
N1*PR*ACME HEALTH PLAN*XX*1234567890~
N1*PE*CITY MEDICAL GROUP*XX*9876543210~
LX*1~
CLP*PCN-2026-001*1*4000.00*3200.00*0.00*MC*CLM-20260101-001~
NM1*QC*1*DOE*JANE****MI*MBR-00112233~
NM1*82*1*SMITH*JOHN****XX*1234567892~
SVC*HC:93458*2000.00*1500.00**1~
DTM*472*20260101~
CAS*CO*45*500.00~
SVC*HC:93306*2000.00*1700.00**1~
DTM*472*20260101~
CAS*CO*45*300.00~
SE*17*0001~
GE*1*1~
IEA*1*000000001~`

async function analyze835(rawEdi: string): Promise<CaseDetail> {
  const res = await api.post<CaseDetail>('/analyze/835', { raw_edi: rawEdi })
  return res.data
}

export default function Analyze835Page() {
  const navigate = useNavigate()
  const [edi,        setEdi]        = useState('')
  const [result,     setResult]     = useState<CaseDetail | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const mutation = useMutation({
    mutationFn: analyze835,
    onSuccess: (data) => setResult(data),
  })

  function loadSample() {
    setEdi(SAMPLE_835)
  }

  function handleAnalyze() {
    const normalized = edi.trim().replace(/\r\n|\r|\n/g, '')
    if (!normalized) return
    mutation.mutate(normalized)
  }

  function closeModal() {
    if (result) {
      navigate(`/cases/${result.id}`)
    }
    setResult(null)
  }

  const firedDetectors = (result?.detector_results ?? []).filter((d) => d.fired)

  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Analyze 835 EDI</h1>
        <p className="text-sm text-gray-500 mt-1">
          Paste a raw X12 835 remittance advice. OPA will parse the claim, run all detector rules,
          compute priority scores, and open the case automatically.
        </p>
      </div>

      {/* Input card */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 space-y-4">
        <div className="flex items-center justify-between">
          <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Raw X12 835 Document
          </label>
          <button
            onClick={loadSample}
            className="text-xs text-[#FE017D] hover:underline font-medium"
          >
            Load sample 835
          </button>
        </div>

        <textarea
          ref={textareaRef}
          value={edi}
          onChange={(e) => setEdi(e.target.value)}
          rows={16}
          placeholder="ISA*00*          *00*          *ZZ*PAYER…"
          spellCheck={false}
          className="w-full px-4 py-3 font-mono text-xs bg-gray-50 border border-gray-200 rounded-xl
                     focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]
                     text-gray-800 resize-y transition-colors"
        />

        {mutation.isError && (
          <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5">
            <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
            <p className="text-xs text-red-700">
              {(mutation.error as any)?.response?.data?.detail
                ?? (mutation.error as Error)?.message
                ?? 'Analysis failed. Check the EDI format and try again.'}
            </p>
          </div>
        )}

        <button
          onClick={handleAnalyze}
          disabled={!edi.trim() || mutation.isPending}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-[#FE017D] text-white
                     text-sm font-semibold rounded-lg hover:bg-[#e5006f]
                     disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
        >
          {mutation.isPending ? (
            <>
              <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Analyzing…
            </>
          ) : (
            <>
              <Zap className="w-4 h-4" />
              Analyze &amp; Create Case
            </>
          )}
        </button>
      </div>

      {/* Format hint */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
        <div className="flex items-start gap-3">
          <FileText className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
          <div className="text-xs text-blue-700 space-y-1">
            <p className="font-semibold">Expected format: X12 835 Health Care Claim Payment/Advice</p>
            <p>Must begin with <span className="font-mono bg-blue-100 px-1 py-0.5 rounded">ISA*</span> and include at least one
            <span className="font-mono bg-blue-100 px-1 py-0.5 rounded mx-1">CLP*</span> segment.
            Segment terminator is auto-detected from the ISA envelope.
            Multiple claims in one 835 are supported — OPA processes the first claim.</p>
          </div>
        </div>
      </div>

      {/* ── Results modal ───────────────────────────────────────────────────── */}
      {result && (
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
          onClick={(e) => { if (e.target === e.currentTarget) closeModal() }}
        >
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl overflow-hidden">

            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-5 h-5 text-green-500" />
                <h2 className="text-base font-bold text-gray-900">Analysis Complete</h2>
              </div>
              <button
                onClick={closeModal}
                className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Case identity */}
            <div className="px-6 pt-5 pb-4 border-b border-gray-100">
              <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">Case Number</p>
              <p className="text-xl font-bold font-mono text-gray-900 mb-2">{result.case_number}</p>
              <div className="flex items-center flex-wrap gap-2">
                <PriorityBadge priority={result.priority} />
                <StatusBadge status={result.status} />
                {firedDetectors.map((d) => (
                  <span key={d.detector_id} className="inline-flex items-center gap-1.5">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold ${detectorBadge[d.detector_id] ?? 'bg-gray-100 text-gray-600'}`}>
                      {d.detector_id}
                    </span>
                    <span className="text-sm text-gray-700">
                      {d.finding?.finding_type ?? d.detector_name}
                    </span>
                  </span>
                ))}
                {firedDetectors.length === 0 && (
                  <span className="text-xs text-gray-400 italic">No detectors fired</span>
                )}
              </div>
            </div>

            {/* Metrics */}
            <div className="px-6 py-4 grid grid-cols-2 sm:grid-cols-4 gap-4 border-b border-gray-100">
              {[
                { label: 'Billed',         value: formatCurrency(result.claim?.total_billed ?? 0) },
                { label: 'Paid',           value: formatCurrency(result.claim?.total_paid   ?? 0) },
                { label: 'At Risk',        value: formatCurrency(result.amount_at_risk),      highlight: result.amount_at_risk > 0 },
                { label: 'Priority Score', value: `${result.priority_score.toFixed(1)} / 100` },
              ].map(({ label, value, highlight }) => (
                <div key={label} className="bg-gray-50 rounded-xl p-3 text-center">
                  <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1">{label}</p>
                  <p className={`text-lg font-bold ${highlight ? 'text-red-600' : 'text-gray-900'}`}>{value}</p>
                </div>
              ))}
            </div>

            {/* Priority breakdown */}
            {result.priority_breakdown && (
              <div className="px-6 py-4 border-b border-gray-100 space-y-2.5">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Priority Breakdown</p>
                {[
                  { label: `Amount at Risk  (${formatCurrency(result.priority_breakdown.amount_at_risk)})`, pts: result.priority_breakdown.amount_pts, max: 40, color: 'bg-blue-400' },
                  { label: `Likelihood  (${Math.round(result.priority_breakdown.likelihood_score * 100)}%)`, pts: result.priority_breakdown.likelihood_pts, max: 40, color: 'bg-indigo-400' },
                  { label: 'Urgency', pts: result.priority_breakdown.urgency_pts, max: 20, color: result.priority_breakdown.urgency_override_applied ? 'bg-red-500' : 'bg-orange-400' },
                ].map(({ label, pts, max, color }) => (
                  <div key={label} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="text-gray-600">{label}</span>
                      <span className="font-semibold text-gray-800">{pts.toFixed(1)} / {max} pts</span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                      <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${Math.min((pts / max) * 100, 100)}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Footer */}
            <div className="px-6 py-4 flex items-center justify-between bg-gray-50">
              <p className="text-xs text-gray-500">
                Case added to worklist · LOB: <span className="font-semibold">{result.lob}</span>
              </p>
              <button
                onClick={closeModal}
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-[#FE017D] text-white
                           text-sm font-semibold rounded-lg hover:bg-[#e5006f] transition-colors"
              >
                View Full Case →
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
