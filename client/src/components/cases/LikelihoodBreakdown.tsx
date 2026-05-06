import type { LikelihoodBreakdown, ClaimFinding } from '../../types'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell,
} from 'recharts'

interface Props {
  breakdown: LikelihoodBreakdown
  findings?: ClaimFinding[]
}

const COMPONENTS = [
  { key: 'cpt_risk_score',        label: 'CPT Risk',         weight: 0.30, color: '#ef4444' },
  { key: 'provider_risk_tier',    label: 'Provider Risk',    weight: 0.25, color: '#f97316' },
  { key: 'dx_cpt_mismatch_score', label: 'DX/CPT Mismatch', weight: 0.20, color: '#eab308' },
  { key: 'claim_complexity_score',label: 'Claim Complexity', weight: 0.15, color: '#3b82f6' },
  { key: 'billing_variance_score',label: 'Billing Variance', weight: 0.10, color: '#8b5cf6' },
] as const

type ComponentKey = typeof COMPONENTS[number]['key']

const DETECTOR_COMPONENT: Record<string, string> = {
  'DX_CPT_MISMATCH_V1':       'cpt_risk_score',
  'UPCODING_V1':               'cpt_risk_score',
  'EXCESS_UNITS_V1':           'cpt_risk_score',
  'BILLING_VARIANCE_V1':       'billing_variance_score',
  'MULTI_LINE_COMPLEXITY_V1':  'claim_complexity_score',
  'DUPLICATE_CLAIM_V1':        'claim_complexity_score',
  'POST_DEATH_V1':             'provider_risk_tier',
  'RETRO_TERM_V1':             'provider_risk_tier',
  'GENERAL_REVIEW_V1':         'dx_cpt_mismatch_score',
  'DET-05': 'cpt_risk_score',
  'DET-03': 'cpt_risk_score',
  'DET-06': 'cpt_risk_score',
  'DET-04': 'billing_variance_score',
  'DET-01': 'claim_complexity_score',
  'DET-02': 'claim_complexity_score',
}

interface ChartEntry {
  label: string
  contribution: number
  weight: number
  color: string
  rawScore: number
  hasFired: boolean
}

export default function LikelihoodBreakdownChart({ breakdown, findings = [] }: Props) {
  const firedComponents = new Set<string>()
  for (const f of findings) {
    const comp = DETECTOR_COMPONENT[f.detector_code]
    if (comp) firedComponents.add(comp)
  }

  const chartData: ChartEntry[] = COMPONENTS.map((c) => {
    const rawScore   = breakdown[c.key as ComponentKey] as number
    const normalized = c.key === 'provider_risk_tier' ? rawScore / 5 : rawScore
    return {
      label:        c.label,
      contribution: parseFloat((normalized * c.weight * 100).toFixed(1)),
      weight:       c.weight,
      color:        c.color,
      rawScore,
      hasFired:     firedComponents.has(c.key),
    }
  })

  const scorePercent = Math.round(breakdown.likelihood_score * 100)
  let scoreColor = 'text-green-600'
  if (scorePercent >= 70) scoreColor = 'text-red-600'
  else if (scorePercent >= 50) scoreColor = 'text-yellow-600'

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Likelihood Breakdown</h3>

      <ResponsiveContainer width="100%" height={180}>
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 0, right: 16, left: 0, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" domain={[0, 30]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 10 }} />
          <YAxis type="category" dataKey="label" width={110} tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={(value: number, _name: string, props: { payload?: ChartEntry }) => {
              const entry = props.payload
              if (!entry) return [`${value}%`, 'Contribution']
              return [
                `${value}% contribution (raw: ${typeof entry.rawScore === 'number' ? entry.rawScore.toFixed(2) : entry.rawScore})`,
                `Weight: ${Math.round(entry.weight * 100)}%`,
              ]
            }}
          />
          <Bar dataKey="contribution" radius={[0, 4, 4, 0]}>
            {chartData.map((entry, idx) => (
              <Cell key={idx} fill={entry.color} fillOpacity={entry.hasFired ? 1 : 0.35} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div className="mt-4 pt-4 border-t border-gray-100 flex items-center justify-between">
        <span className="text-sm text-gray-500 font-medium">Overall Likelihood Score</span>
        <span className={`text-2xl font-bold ${scoreColor}`}>{scorePercent}%</span>
      </div>
    </div>
  )
}
