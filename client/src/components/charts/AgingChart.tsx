import type { AgingBucket } from '../../types'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { formatCurrency } from '../../utils/formatUtils'

interface Props {
  data: AgingBucket[]
}

const BUCKET_COLORS: Record<string, string> = {
  '0-15d': '#22c55e',
  '16-30d': '#eab308',
  '31-45d': '#f97316',
  '46-60d': '#ef4444',
  '60+d': '#991b1b',
}

function getBucketColor(label: string): string {
  return BUCKET_COLORS[label] ?? '#6b7280'
}

interface TooltipPayload {
  payload: AgingBucket
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-white border border-gray-200 rounded shadow-lg p-3 text-sm">
      <p className="font-semibold text-gray-800 mb-1">{d.label}</p>
      <p className="text-gray-600">Cases: <span className="font-medium text-gray-900">{d.count}</span></p>
      <p className="text-gray-600">At Risk: <span className="font-medium text-gray-900">{formatCurrency(d.amount)}</span></p>
    </div>
  )
}

export default function AgingChart({ data }: Props) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Case Aging Distribution</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 12 }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
          <Tooltip content={<CustomTooltip />} />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {data.map((entry, idx) => (
              <Cell key={idx} fill={getBucketColor(entry.label)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
