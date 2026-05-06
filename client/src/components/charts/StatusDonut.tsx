import type { StatusCount } from '../../types'
import type { CaseStatus } from '../../types'
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { statusLabel } from '../../utils/priorityUtils'

interface Props {
  data: StatusCount[]
}

const STATUS_COLORS: Record<string, string> = {
  new: '#6b7280',
  assigned: '#3b82f6',
  in_review: '#6366f1',
  pending_supervisor: '#8b5cf6',
  notice_sent: '#f97316',
  provider_responded: '#06b6d4',
  reconciling: '#14b8a6',
  closed_recovered: '#22c55e',
  closed_written_off: '#ef4444',
  closed_overturned: '#eab308',
  closed_no_overpayment: '#94a3b8',
}

function getStatusColor(status: string): string {
  return STATUS_COLORS[status] ?? '#9ca3af'
}

function isCaseStatus(s: string): s is CaseStatus {
  return s in STATUS_COLORS
}

interface TooltipPayload {
  payload: StatusCount
  value: number
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayload[] }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-white border border-gray-200 rounded shadow-lg p-2 text-sm">
      <p className="font-medium text-gray-800">
        {isCaseStatus(d.status) ? statusLabel(d.status) : d.status}
      </p>
      <p className="text-gray-500">{d.count} cases</p>
    </div>
  )
}

export default function StatusDonut({ data }: Props) {
  const total = data.reduce((sum, d) => sum + d.count, 0)

  const chartData = data.map((d) => ({
    ...d,
    name: isCaseStatus(d.status) ? statusLabel(d.status) : d.status,
  }))

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">Status Distribution</h3>
      <div className="relative">
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="45%"
              innerRadius={55}
              outerRadius={85}
              paddingAngle={2}
              dataKey="count"
            >
              {chartData.map((entry, idx) => (
                <Cell key={idx} fill={getStatusColor(entry.status)} />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
            <Legend
              iconType="circle"
              iconSize={8}
              wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none" style={{ top: '-12px' }}>
          <div className="text-center">
            <p className="text-2xl font-bold text-gray-900">{total}</p>
            <p className="text-xs text-gray-400">Total</p>
          </div>
        </div>
      </div>
    </div>
  )
}
