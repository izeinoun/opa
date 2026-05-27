import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'
import { DollarSign, CheckCircle, Clock, BarChart3 } from 'lucide-react'
import { formatCurrency } from '../../utils/formatUtils'

export type Period = 'week' | 'month' | 'quarter'

export interface PerformanceData {
  period: Period
  period_start: string
  period_end: string
  cases_closed: number
  dollars_recovered: number
  dollars_written_off: number
  avg_handle_time_days: number | null
  disposition_breakdown: { disposition: string; count: number }[]
  pipeline_snapshot: { status: string; count: number }[]
  cases_closed_by_week: { week_start: string; count: number }[]
  pipeline_total_active: number
}

const PERIOD_LABEL: Record<Period, string> = {
  week: 'Past 7 days', month: 'Past 30 days', quarter: 'Past 90 days',
}

const DISPOSITION_LABEL: Record<string, string> = {
  closed_recovered: 'Recovered', closed_written_off: 'Written off',
  closed_overturned: 'Overturned', closed_no_overpayment: 'No overpayment',
  closed_unrecoverable: 'Unrecoverable',
}

const STATUS_LABEL: Record<string, string> = {
  new: 'New', assigned: 'Assigned', in_review: 'In Review',
  ready_for_notice: 'Ready for Notice', pending_supervisor: 'Pending Supervisor',
  notice_sent: 'Notice Sent', provider_responded: 'Provider Responded',
  reconciling: 'Reconciling',
}

const STATUS_COLOR: Record<string, string> = {
  new: '#6b7280', assigned: '#2563eb', in_review: '#f59e0b',
  ready_for_notice: '#4f46e5', pending_supervisor: '#9333ea',
  notice_sent: '#14b8a6', provider_responded: '#3b82f6', reconciling: '#d97706',
}

interface Props {
  data?: PerformanceData
  isLoading: boolean
  pipelineLabel?: string
}

export default function PerformanceView({ data, isLoading, pipelineLabel = 'Active pipeline' }: Props) {
  return (
    <div className="space-y-5">
      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard icon={CheckCircle} label="Cases closed" tint="green"
          value={isLoading ? '…' : String(data?.cases_closed ?? 0)} />
        <KpiCard icon={DollarSign} label="$ Recovered" tint="emerald"
          value={isLoading ? '…' : formatCurrency(data?.dollars_recovered ?? 0)} />
        <KpiCard icon={BarChart3} label="$ Written off" tint="gray"
          value={isLoading ? '…' : formatCurrency(data?.dollars_written_off ?? 0)} />
        <KpiCard icon={Clock} label="Avg handle time" tint="amber"
          subtext="open → closed"
          value={isLoading ? '…' : (data?.avg_handle_time_days != null ? `${data.avg_handle_time_days} days` : '—')} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Cases closed per week */}
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Cases closed per week</h3>
          {isLoading ? (
            <div className="h-64 bg-gray-50 animate-pulse rounded" />
          ) : !data?.cases_closed_by_week?.length ? (
            <p className="text-sm text-gray-400 italic">No data.</p>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data.cases_closed_by_week} margin={{ top: 5, right: 5, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                <XAxis dataKey="week_start" tickFormatter={(v) => v.slice(5)} tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ fontSize: '12px', borderRadius: '8px', border: '1px solid #e5e7eb' }}
                  labelFormatter={(v) => `Week of ${v}`}
                />
                <Bar dataKey="count" fill="#6366f1" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Pipeline snapshot */}
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-baseline justify-between mb-3">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{pipelineLabel}</h3>
            <span className="text-xs text-gray-400">{data?.pipeline_total_active ?? 0} cases</span>
          </div>
          {isLoading ? (
            <div className="h-32 bg-gray-50 animate-pulse rounded" />
          ) : !data?.pipeline_snapshot?.length ? (
            <p className="text-sm text-gray-400 italic">No open cases.</p>
          ) : (
            <ul className="space-y-2">
              {data.pipeline_snapshot.map((b) => {
                const color = STATUS_COLOR[b.status] ?? '#6b7280'
                const max = Math.max(...data.pipeline_snapshot.map((x) => x.count), 1)
                const pct = (b.count / max) * 100
                return (
                  <li key={b.status}>
                    <div className="flex items-baseline justify-between text-xs mb-1">
                      <span className="text-gray-700 font-medium">{STATUS_LABEL[b.status] ?? b.status}</span>
                      <span className="text-gray-500 tabular-nums font-mono">{b.count}</span>
                    </div>
                    <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>

      {data && data.disposition_breakdown.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
            Closures by disposition · {PERIOD_LABEL[data.period]}
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {data.disposition_breakdown.map((d) => (
              <div key={d.disposition} className="border border-gray-100 rounded-lg p-3">
                <p className="text-[11px] text-gray-500 uppercase tracking-wider mb-1">
                  {DISPOSITION_LABEL[d.disposition] ?? d.disposition}
                </p>
                <p className="text-xl font-bold text-gray-900 tabular-nums">{d.count}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function KpiCard({
  icon: Icon, label, value, tint, subtext,
}: { icon: any; label: string; value: string; tint: 'green' | 'emerald' | 'gray' | 'amber'; subtext?: string }) {
  const tintBg: Record<string, string> = {
    green: 'bg-green-50 text-green-700',
    emerald: 'bg-emerald-50 text-emerald-700',
    gray: 'bg-gray-100 text-gray-600',
    amber: 'bg-amber-50 text-amber-700',
  }
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-2">
        <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${tintBg[tint]}`}>
          <Icon className="w-4 h-4" />
        </div>
        <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">{label}</span>
      </div>
      <p className="text-2xl font-bold text-gray-900 tabular-nums">{value}</p>
      {subtext && <p className="text-[11px] text-gray-400 mt-1">{subtext}</p>}
    </div>
  )
}

export function PeriodToggle({ period, onChange }: { period: Period; onChange: (p: Period) => void }) {
  return (
    <div className="inline-flex bg-gray-100 rounded-lg p-0.5">
      {(['week', 'month', 'quarter'] as Period[]).map((p) => (
        <button key={p}
          onClick={() => onChange(p)}
          className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
            period === p ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          {p === 'week' ? 'Week' : p === 'month' ? 'Month' : 'Quarter'}
        </button>
      ))}
    </div>
  )
}
