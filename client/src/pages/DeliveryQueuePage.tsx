import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { AlertCircle, Mail, HardDrive, Clock } from 'lucide-react'
import api from '../services/api'

interface DeliveryItem {
  case_id: string
  case_number: string
  claim_id: string
  provider_name: string
  provider_npi: string
  member_id: string
  lob: string
  amount_at_risk: number
  deadline: string
  deadline_date: string
  status: string
  delivery_mode: string
  playbook: Record<string, any>
}

const STATUS_COLORS: Record<string, { bg: string; text: string; icon: React.ReactNode }> = {
  ready_to_send: { bg: 'bg-blue-50', text: 'text-blue-700', icon: <Clock className="w-4 h-4" /> },
  notice_sent: { bg: 'bg-purple-50', text: 'text-purple-700', icon: <Mail className="w-4 h-4" /> },
  letter_accessed: { bg: 'bg-green-50', text: 'text-green-700', icon: <AlertCircle className="w-4 h-4" /> },
  letter_sent: { bg: 'bg-green-50', text: 'text-green-700', icon: <HardDrive className="w-4 h-4" /> },
  delivery_failed: { bg: 'bg-red-50', text: 'text-red-700', icon: <AlertCircle className="w-4 h-4" /> },
  needs_review: { bg: 'bg-amber-50', text: 'text-amber-700', icon: <AlertCircle className="w-4 h-4" /> },
}

async function fetchDeliveryQueue(mode?: string): Promise<DeliveryItem[]> {
  const url = mode ? `/cases/delivery-queue?mode=${mode}` : '/cases/delivery-queue'
  const res = await api.get<DeliveryItem[]>(url)
  return res.data
}

export default function DeliveryQueuePage() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<string | null>(null)

  const { data: items = [], isLoading } = useQuery<DeliveryItem[]>({
    queryKey: ['delivery-queue', mode],
    queryFn: () => fetchDeliveryQueue(mode || undefined),
  })

  const allStatuses = Array.from(new Set(items.map((i) => i.status)))
  const allModes = Array.from(new Set(items.map((i) => i.delivery_mode)))

  return (
    <div className="max-w-7xl space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Delivery Queue</h1>
        <p className="text-gray-600 mt-1">
          Monitor all cases in the delivery pipeline, from queued to delivered.
        </p>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <div className="flex items-center gap-4">
            <div className="flex gap-2">
              <button
                onClick={() => setMode(null)}
                className={`px-3 py-1 rounded-full text-sm font-semibold transition-colors ${
                  mode === null
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                All Modes
              </button>
              {allModes.map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`px-3 py-1 rounded-full text-sm font-semibold transition-colors ${
                    mode === m
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  {m === 'email' ? '📧 Email' : '📁 Portal'}
                </button>
              ))}
            </div>
            <span className="text-sm text-gray-600 ml-auto">
              {items.length} case{items.length === 1 ? '' : 's'}
            </span>
          </div>
        </div>

        {isLoading ? (
          <div className="p-6 text-center text-gray-500">Loading delivery queue...</div>
        ) : items.length === 0 ? (
          <div className="p-6 text-center text-gray-500">No cases in delivery queue</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700">Case</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700">Provider</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700">Member</th>
                  <th className="px-4 py-3 text-right text-sm font-semibold text-gray-700">At Risk</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700">Deadline</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700">Mode</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700">Status</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {items.map((item) => {
                  const statusColor = STATUS_COLORS[item.status] || { bg: 'bg-gray-50', text: 'text-gray-700', icon: null }
                  const isOverdue = new Date(item.deadline_date) < new Date()
                  return (
                    <tr key={item.case_id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3 text-sm font-mono text-gray-900">{item.case_number}</td>
                      <td className="px-4 py-3 text-sm text-gray-900">{item.provider_name}</td>
                      <td className="px-4 py-3 text-sm text-gray-700">{item.member_id.slice(0, 12)}...</td>
                      <td className="px-4 py-3 text-sm text-right font-semibold text-gray-900">
                        ${item.amount_at_risk?.toFixed(2) || '0.00'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">
                        <div className={isOverdue ? 'text-red-600 font-semibold' : ''}>
                          {new Date(item.deadline_date).toLocaleDateString()}
                          {isOverdue && <span className="ml-1 text-xs">(OVERDUE)</span>}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <span className="inline-block px-2 py-1 rounded-full text-xs font-semibold bg-gray-100 text-gray-700">
                          {item.delivery_mode === 'email' ? '📧 Email' : '📁 Portal'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <div className={`inline-flex items-center gap-2 px-2 py-1 rounded-full text-xs font-semibold ${statusColor.bg} ${statusColor.text}`}>
                          {statusColor.icon}
                          {item.status.replace(/_/g, ' ')}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <button
                          onClick={() => navigate(`/cases/${item.case_id}`)}
                          className="text-blue-600 hover:text-blue-800 font-semibold transition-colors"
                        >
                          View Case →
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
