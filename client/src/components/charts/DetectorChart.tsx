import type { DetectorStat } from '../../types'
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
import { detectorLabel } from '../../utils/priorityUtils'

interface Props {
  data: DetectorStat[]
}

function confidenceToColor(confidence: number): string {
  if (confidence >= 0.8) return '#ef4444'
  if (confidence >= 0.6) return '#f97316'
  if (confidence >= 0.4) return '#eab308'
  return '#22c55e'
}

interface TooltipPayload {
  payload: DetectorStat
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
  const d = payload[0].payload
  return (
    <div className="bg-white border border-gray-200 rounded shadow-lg p-3 text-sm">
      <p className="font-semibold text-gray-800 mb-1">{label}</p>
      <p className="text-xs text-gray-500 mb-2">{detectorLabel(d.detector_code)}</p>
      <p className="text-gray-600">Total Findings: <span className="font-medium">{d.total_findings}</span></p>
      <p className="text-gray-600">Confirmed: <span className="font-medium">{formatCurrency(d.confirmed_overpayment)}</span></p>
      <p className="text-gray-600">Avg Confidence: <span className="font-medium">{(d.avg_confidence * 100).toFixed(0)}%</span></p>
    </div>
  )
}

export default function DetectorChart({ data }: Props) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-1">Detector Performance</h3>
      <p className="text-xs text-gray-400 mb-4">Bar color = avg confidence (green=low, red=high)</p>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="detector_code" tick={{ fontSize: 11 }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
          <Tooltip content={<CustomTooltip />} />
          <Bar dataKey="total_findings" name="Total Findings" radius={[4, 4, 0, 0]}>
            {data.map((entry, idx) => (
              <Cell key={idx} fill={confidenceToColor(entry.avg_confidence)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
