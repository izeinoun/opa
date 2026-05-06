import type { WorkloadItem } from '../../types'
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { formatCurrency } from '../../utils/formatUtils'

interface Props {
  data: WorkloadItem[]
}

interface ChartEntry extends WorkloadItem {
  other_cases: number
}

interface TooltipPayload {
  payload: ChartEntry
  dataKey: string
  value: number
  color: string
  name: string
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean
  payload?: TooltipPayload[]
  label?: string
}) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  return (
    <div className="bg-white border border-gray-200 rounded shadow-lg p-3 text-sm min-w-[180px]">
      <p className="font-semibold text-gray-800 mb-2">{label}</p>
      <p className="text-red-600">High Priority: <span className="font-medium">{d?.high_priority}</span></p>
      <p className="text-blue-600">Other Open: <span className="font-medium">{d?.other_cases}</span></p>
      <p className="text-gray-600">Total At Risk: <span className="font-medium">{formatCurrency(d?.total_at_risk ?? 0)}</span></p>
    </div>
  )
}

export default function WorkloadChart({ data }: Props) {
  const chartData: ChartEntry[] = data.map((d) => ({
    ...d,
    other_cases: Math.max(0, d.open_cases - d.high_priority),
  }))

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Analyst Workload</h3>
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={chartData} margin={{ top: 4, right: 40, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="assignee" tick={{ fontSize: 11 }} />
          <YAxis yAxisId="left" allowDecimals={false} tick={{ fontSize: 12 }} />
          <YAxis
            yAxisId="right"
            orientation="right"
            tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
            tick={{ fontSize: 11 }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar yAxisId="left" dataKey="high_priority" name="High Priority" stackId="a" fill="#ef4444" radius={[0, 0, 0, 0]} />
          <Bar yAxisId="left" dataKey="other_cases" name="Other Open" stackId="a" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="total_at_risk"
            name="At Risk ($)"
            stroke="#8b5cf6"
            strokeWidth={2}
            dot={{ r: 4 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
