import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { ArrowLeft, Save, AlertCircle } from 'lucide-react'
import { useState, useEffect } from 'react'
import api from '../services/api'

interface FeeScheduleRow {
  fee_schedule_id: string
  lob: string
  cpt_code: string
  cpt_description: string | null
  effective_date: string
  termination_date: string | null
  base_rate: number
  rate_basis: string
  modifier_applicable: string | null
}

interface ContractLimitationRow {
  limitation_id: string
  cpt_code: string
  limitation_type: string
  limitation_value: string
  effective_date: string
  description: string
}

interface OrgDetail {
  provider_org_id: string
  name: string
  npi: string
  tin: string
  org_type: string
  fee_schedules: FeeScheduleRow[]
  contract_limitations: ContractLimitationRow[]
}

interface Playbook {
  playbook_id: string
  provider_org_id: string
  delivery_type: string
  status: string
  target_url: string | null
  contact_email: string | null
  contact_name: string | null
  email_template_ref: string | null
  notes: string | null
  auth_config: Record<string, any> | null
  preflight_checks: Array<Record<string, any>> | null
  navigation_steps: Array<Record<string, any>> | null
  confirmation_config: Record<string, any> | null
  failure_signals: Array<Record<string, any>> | null
  post_run_config: Record<string, any> | null
  last_validated_at: string | null
  created_at: string
  updated_at: string
}

async function fetchOrgDetail(id: string): Promise<OrgDetail> {
  const res = await api.get<OrgDetail>(`/fee-schedules/${id}`)
  return res.data
}

async function fetchPlaybook(id: string): Promise<Playbook | null> {
  try {
    const res = await api.get<Playbook>(`/fee-schedules/${id}/playbook`)
    return res.data
  } catch {
    return null
  }
}

export default function ProviderOrgDetailPage() {
  const { orgId } = useParams<{ orgId: string }>()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<'schedules' | 'playbook'>('schedules')
  const [playbookData, setPlaybookData] = useState<Partial<Playbook>>({})
  const [saveMessage, setSaveMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  if (!orgId) return <div>Invalid org ID</div>

  const { data: orgDetail, isLoading: orgLoading } = useQuery<OrgDetail>({
    queryKey: ['provider-org-detail', orgId],
    queryFn: () => fetchOrgDetail(orgId),
  })

  const { data: playbook } = useQuery<Playbook | null>({
    queryKey: ['playbook', orgId],
    queryFn: () => fetchPlaybook(orgId),
  })

  // Load playbook data into form state when it arrives
  useEffect(() => {
    if (playbook) {
      setPlaybookData(playbook)
    }
  }, [playbook])

  const savePlaybookMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        delivery_type: playbookData.delivery_type || 'email',
        status: playbookData.status || 'draft',
        target_url: playbookData.target_url,
        contact_email: playbookData.contact_email,
        contact_name: playbookData.contact_name,
        email_template_ref: playbookData.email_template_ref,
        notes: playbookData.notes,
        auth_config: playbookData.auth_config,
        preflight_checks: playbookData.preflight_checks,
        navigation_steps: playbookData.navigation_steps,
        confirmation_config: playbookData.confirmation_config,
        failure_signals: playbookData.failure_signals,
        post_run_config: playbookData.post_run_config,
      }
      const res = await api.put<Playbook>(`/fee-schedules/${orgId}/playbook`, payload)
      return res.data
    },
    onSuccess: (data) => {
      setPlaybookData(data)
      setSaveMessage({ type: 'success', text: 'Playbook saved successfully' })
      setTimeout(() => setSaveMessage(null), 3000)
    },
    onError: (error: any) => {
      setSaveMessage({ type: 'error', text: error.response?.data?.detail || 'Failed to save playbook' })
    },
  })

  if (orgLoading) return <div className="p-6">Loading...</div>
  if (!orgDetail) return <div className="p-6">Provider org not found</div>

  return (
    <div className="max-w-6xl">
      <button onClick={() => navigate('/fee-schedules')} className="flex items-center gap-1 text-blue-600 hover:text-blue-800 mb-4">
        <ArrowLeft className="w-4 h-4" /> Back to Fee Schedules
      </button>

      <div className="bg-white rounded-lg border border-gray-200 p-6 mb-6">
        <h1 className="text-3xl font-bold text-gray-900">{orgDetail.name}</h1>
        <div className="grid grid-cols-3 gap-4 mt-4 text-sm">
          <div>
            <span className="text-gray-500">NPI</span>
            <p className="font-mono text-gray-900">{orgDetail.npi}</p>
          </div>
          <div>
            <span className="text-gray-500">TIN</span>
            <p className="font-mono text-gray-900">{orgDetail.tin}</p>
          </div>
          <div>
            <span className="text-gray-500">Type</span>
            <p className="text-gray-900">{orgDetail.org_type}</p>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="flex border-b border-gray-200">
          <button
            onClick={() => setActiveTab('schedules')}
            className={`flex-1 px-6 py-4 text-sm font-semibold transition-colors ${
              activeTab === 'schedules'
                ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            Fee Schedules ({orgDetail.fee_schedules.length})
          </button>
          <button
            onClick={() => setActiveTab('playbook')}
            className={`flex-1 px-6 py-4 text-sm font-semibold transition-colors ${
              activeTab === 'playbook'
                ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                : 'text-gray-600 hover:text-gray-800'
            }`}
          >
            Delivery Playbook
          </button>
        </div>

        <div className="p-6">
          {activeTab === 'schedules' && (
            <div className="space-y-4">
              {orgDetail.fee_schedules.length === 0 ? (
                <p className="text-gray-500">No fee schedules configured</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 border-b border-gray-200">
                      <tr>
                        <th className="px-4 py-2 text-left font-semibold text-gray-700">CPT Code</th>
                        <th className="px-4 py-2 text-left font-semibold text-gray-700">Description</th>
                        <th className="px-4 py-2 text-left font-semibold text-gray-700">LOB</th>
                        <th className="px-4 py-2 text-left font-semibold text-gray-700">Effective</th>
                        <th className="px-4 py-2 text-right font-semibold text-gray-700">Base Rate</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      {orgDetail.fee_schedules.map((row) => (
                        <tr key={row.fee_schedule_id} className="hover:bg-gray-50">
                          <td className="px-4 py-2 font-mono text-gray-900">{row.cpt_code}</td>
                          <td className="px-4 py-2 text-gray-700">{row.cpt_description || '—'}</td>
                          <td className="px-4 py-2 text-gray-700">{row.lob}</td>
                          <td className="px-4 py-2 text-gray-700">{row.effective_date}</td>
                          <td className="px-4 py-2 text-right font-mono text-gray-900">${row.base_rate.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {activeTab === 'playbook' && (
            <PlaybookEditor playbook={playbookData} setPlaybook={setPlaybookData} onSave={() => savePlaybookMutation.mutate()} isSaving={savePlaybookMutation.isPending} saveMessage={saveMessage} />
          )}
        </div>
      </div>
    </div>
  )
}

function PlaybookEditor({
  playbook,
  setPlaybook,
  onSave,
  isSaving,
  saveMessage,
}: {
  playbook: Partial<Playbook>
  setPlaybook: (pb: Partial<Playbook>) => void
  onSave: () => void
  isSaving: boolean
  saveMessage: { type: 'success' | 'error'; text: string } | null
}) {
  return (
    <div className="space-y-6">
      {saveMessage && (
        <div className={`p-3 rounded-lg flex items-center gap-2 ${saveMessage.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'}`}>
          <AlertCircle className="w-4 h-4" />
          {saveMessage.text}
        </div>
      )}

      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-gray-900">Delivery Configuration</h3>

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">Delivery Type</label>
          <select
            value={playbook.delivery_type || 'email'}
            onChange={(e) => setPlaybook({ ...playbook, delivery_type: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            <option value="email">Email (Secure Link)</option>
            <option value="portal">Portal (Agent Delivery)</option>
          </select>
        </div>

        {playbook.delivery_type === 'email' && (
          <>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">Contact Email *</label>
                <input
                  type="email"
                  value={playbook.contact_email || ''}
                  onChange={(e) => setPlaybook({ ...playbook, contact_email: e.target.value })}
                  placeholder="billing@provider.com"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">Contact Name</label>
                <input
                  type="text"
                  value={playbook.contact_name || ''}
                  onChange={(e) => setPlaybook({ ...playbook, contact_name: e.target.value })}
                  placeholder="John Doe"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">Email Template</label>
              <select
                value={playbook.email_template_ref || ''}
                onChange={(e) => setPlaybook({ ...playbook, email_template_ref: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="">Default - Secure Download Link</option>
                <option value="secure_link">Secure Download Link</option>
                <option value="otp">One-Time Password (OTP)</option>
                <option value="notify_payer">Payer Notification</option>
              </select>
            </div>
          </>
        )}

        {playbook.delivery_type === 'portal' && (
          <>
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">Portal URL</label>
              <input
                type="url"
                value={playbook.target_url || ''}
                onChange={(e) => setPlaybook({ ...playbook, target_url: e.target.value })}
                placeholder="https://provider-portal.com/upload"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-800">
              Portal delivery is controlled by an external agent. Configure authentication, navigation steps, and success criteria using the advanced options below.
            </div>
          </>
        )}

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">Status</label>
          <select
            value={playbook.status || 'draft'}
            onChange={(e) => setPlaybook({ ...playbook, status: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            <option value="draft">Draft</option>
            <option value="active">Active</option>
            <option value="needs_update">Needs Update</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">Notes</label>
          <textarea
            value={playbook.notes || ''}
            onChange={(e) => setPlaybook({ ...playbook, notes: e.target.value })}
            placeholder="Document any provider-specific quirks, known issues, or special instructions..."
            rows={4}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>

        <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
          <p className="font-semibold mb-1">Portal Configuration</p>
          <p>
            For portal delivery, you can configure authentication, navigation steps, and success criteria.
            These are managed through the API for advanced use cases.
          </p>
        </div>
      </div>

      <div className="flex justify-end gap-3 border-t border-gray-200 pt-6">
        <button
          onClick={onSave}
          disabled={isSaving}
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 disabled:bg-gray-400 transition-colors"
        >
          <Save className="w-4 h-4" />
          {isSaving ? 'Saving...' : 'Save Playbook'}
        </button>
      </div>
    </div>
  )
}
