import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Save, AlertCircle, Edit2, FileText, Download } from 'lucide-react'
import { useState, useEffect } from 'react'
type TabType = 'overview' | 'plans'
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
  address?: string
  city?: string
  state?: string
  zip?: string
  phone?: string
  contact_email?: string
  contact_name?: string
  billing_variance_score?: number
  is_active?: boolean
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
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<TabType>('overview')
  const [isEditing, setIsEditing] = useState(false)
  const [editData, setEditData] = useState<Partial<OrgDetail>>({})
  const [playbookData, setPlaybookData] = useState<Partial<Playbook>>({})
  const [saveMessage, setSaveMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  if (!orgId) return <div>Invalid provider ID</div>

  const { data: orgDetail, isLoading: orgLoading } = useQuery<OrgDetail>({
    queryKey: ['provider-org-detail', orgId],
    queryFn: () => fetchOrgDetail(orgId),
  })

  const { data: playbook } = useQuery<Playbook | null>({
    queryKey: ['playbook', orgId],
    queryFn: () => fetchPlaybook(orgId),
  })

  useEffect(() => {
    if (orgDetail) {
      setEditData(orgDetail)
    }
  }, [orgDetail])

  useEffect(() => {
    if (playbook) {
      setPlaybookData(playbook)
    }
  }, [playbook])

  const savePlaybookMutation = useMutation({
    mutationFn: async () => {
      // The contact email is edited in the Overview fields (editData); persist it
      // to the org's delivery playbook — that's what the Send-to-Provider flow
      // reads. Guard against the notification dropdown's 'email'/'portal'
      // sentinel values leaking into the address.
      const raw = editData.contact_email ?? playbookData.contact_email
      const email = raw && raw !== 'email' && raw !== 'portal' ? raw : undefined
      const payload = {
        delivery_type: email ? 'email' : (playbookData.delivery_type || 'portal'),
        status: 'active',
        target_url: playbookData.target_url,
        contact_email: email,
        contact_name: editData.contact_name ?? playbookData.contact_name,
        email_template_ref: playbookData.email_template_ref,
        notes: playbookData.notes,
      }
      const res = await api.put<Playbook>(`/fee-schedules/${orgId}/playbook`, payload)
      return res.data
    },
    onSuccess: (data) => {
      setPlaybookData(data)
      setIsEditing(false)
      // Refresh the org detail so the Active/Inactive badge reflects the new email.
      queryClient.invalidateQueries({ queryKey: ['provider-org-detail', orgId] })
      setSaveMessage({ type: 'success', text: 'Provider contact saved' })
      setTimeout(() => setSaveMessage(null), 3000)
    },
    onError: (error: any) => {
      setSaveMessage({ type: 'error', text: error.response?.data?.detail || 'Failed to save' })
    },
  })

  const mockContracts = [
    { id: 'ma-2024', name: 'MA Plan Contract 2024', type: 'MA', year: 2024 },
    { id: 'ppo-2024', name: 'PPO Plan Contract 2024', type: 'PPO', year: 2024 },
    { id: 'hmo-2024', name: 'HMO Plan Contract 2024', type: 'HMO', year: 2024 },
  ]

  const handleDownloadContract = (contractId: string) => {
    // Mock PDF download
    const link = document.createElement('a')
    link.href = `data:application/pdf;base64,JVBERi0xLjQKJeLjz9MNCjEgMCBvYmo8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFI+PmVuZG9iagoyIDAgb2JqPDwvVHlwZS9QYWdlcy9LaWRzWzMgMCBSXS9Db3VudCAxPj5lbmRvYmoKMyAwIG9iajw8L1R5cGUvUGFnZS9QYXJlbnQgMiAwIFIvTWVkaWFCb3hbMCAwIDYxMiA3OTJdL0NvbnRlbnRzIDQgMCBSL1Jlc291cmNlczw8L0ZvbnQ8PC9GMSA1IDAgUj4+Pj4+PmVuZG9iagoyIDAgb2JqPDwvVHlwZS9QYWdlcy9LaWRzWzMgMCBSXS9Db3VudCAxPj5lbmRvYmo=`
    link.download = `${contractId}.pdf`
    link.click()
  }

  if (orgLoading) return <div className="p-6">Loading...</div>
  if (!orgDetail) return <div className="p-6">Provider not found</div>

  const riskLevel = orgDetail.billing_variance_score
    ? orgDetail.billing_variance_score > 0.7
      ? 'high'
      : orgDetail.billing_variance_score > 0.4
        ? 'medium'
        : 'low'
    : 'unknown'

  return (
    <div className="max-w-6xl mx-auto p-6">
      {/* Back Button */}
      <button
        onClick={() => navigate('/providers')}
        className="flex items-center gap-1 text-blue-600 hover:text-blue-800 mb-6"
      >
        <ArrowLeft className="w-4 h-4" /> Back to Providers
      </button>

      {/* Header Card */}
      <div className="bg-white rounded-lg border border-gray-200 p-6 mb-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">{orgDetail.name}</h1>
            <p className="text-gray-600 mt-1">{orgDetail.org_type}</p>
          </div>
          {orgDetail.is_active ? (
            <span className="px-3 py-1 text-sm font-medium bg-green-100 text-green-700 rounded-full">
              Active
            </span>
          ) : (
            <span className="px-3 py-1 text-sm font-medium bg-gray-100 text-gray-600 rounded-full">
              Inactive
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-500">NPI</span>
            <p className="font-mono font-medium text-gray-900">{orgDetail.npi}</p>
          </div>
          <div>
            <span className="text-gray-500">TIN</span>
            <p className="font-mono font-medium text-gray-900">{orgDetail.tin}</p>
          </div>
          <div>
            <span className="text-gray-500">Risk Score</span>
            <p className="font-medium text-gray-900">
              {orgDetail.billing_variance_score ? `${(orgDetail.billing_variance_score * 100).toFixed(0)}%` : 'N/A'}
            </p>
          </div>
          <div>
            <span className="text-gray-500">Risk Level</span>
            <p className={`font-medium ${riskLevel === 'high' ? 'text-red-600' : riskLevel === 'medium' ? 'text-yellow-600' : 'text-green-600'}`}>
              {riskLevel.charAt(0).toUpperCase() + riskLevel.slice(1)}
            </p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="flex border-b border-gray-200">
          {(['overview', 'plans'] as TabType[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 px-6 py-4 text-sm font-semibold transition-colors ${
                activeTab === tab
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                  : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              {tab === 'overview' && 'Overview'}
              {tab === 'plans' && 'Plans'}
            </button>
          ))}
        </div>

        <div className="p-6">
          {/* Overview Tab */}
          {activeTab === 'overview' && (
            <OverviewTab
              orgDetail={orgDetail}
              editData={editData}
              setEditData={setEditData}
              isEditing={isEditing}
              setIsEditing={setIsEditing}
              saveMessage={saveMessage}
              onSave={() => savePlaybookMutation.mutate()}
              saving={savePlaybookMutation.isPending}
            />
          )}

          {/* Plans Tab */}
          {activeTab === 'plans' && (
            <PlansTab
              orgId={orgId}
              mockContracts={mockContracts}
              onDownloadContract={handleDownloadContract}
              orgDetail={orgDetail}
            />
          )}
        </div>
      </div>
    </div>
  )
}

// ── Overview Tab ──
const PINK = '#FE017D'

// Defined at module scope (NOT inside OverviewTab) so its component identity is
// stable across renders. A component defined inside another component's body is a
// new type on every render, which unmounts/remounts its inputs and drops focus
// after each keystroke.
function FieldRow({
  label,
  value,
  editable = false,
  onEdit,
  type = 'text',
  isEditing = false,
}: {
  label: string
  value: string | React.ReactNode
  editable?: boolean
  onEdit?: (value: string) => void
  type?: string
  isEditing?: boolean
}) {
  return (
    <div className="flex items-center gap-4 py-3 border-b border-gray-100 last:border-0">
      <label className="text-base font-bold" style={{ color: PINK, minWidth: '160px' }}>
        {label}:
      </label>
      {editable && isEditing ? (
        <input
          type={type}
          value={value as string}
          onChange={(e) => onEdit?.(e.target.value)}
          maxLength={type === 'state' ? 2 : undefined}
          className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
        />
      ) : (
        <span className="text-sm text-gray-900 flex-1">{value || 'Not provided'}</span>
      )}
    </div>
  )
}

function OverviewTab({
  orgDetail,
  editData,
  setEditData,
  isEditing,
  setIsEditing,
  saveMessage,
  onSave,
  saving,
}: {
  orgDetail: OrgDetail
  editData: Partial<OrgDetail>
  setEditData: (data: Partial<OrgDetail>) => void
  isEditing: boolean
  setIsEditing: (editing: boolean) => void
  saveMessage: { type: 'success' | 'error'; text: string } | null
  onSave: () => void
  saving?: boolean
}) {
  return (
    <div className="space-y-6 max-w-3xl">
      {saveMessage && (
        <div
          className={`p-3 rounded-lg flex items-center gap-2 ${
            saveMessage.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'
          }`}
        >
          <AlertCircle className="w-4 h-4" />
          {saveMessage.text}
        </div>
      )}

      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-gray-900">Provider Information</h3>
        {!isEditing && (
          <button
            onClick={() => setIsEditing(true)}
            className="inline-flex items-center gap-2 px-3 py-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
          >
            <Edit2 className="w-4 h-4" />
            Edit
          </button>
        )}
      </div>

      <div className="space-y-6">
        {/* Organization Details */}
        <div>
          <h4 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-3">Organization</h4>
          <div className="space-y-0">
            <FieldRow label="Name" value={editData.name || orgDetail.name} editable isEditing={isEditing} onEdit={(v) => setEditData({ ...editData, name: v })} />
            <FieldRow label="Type" value={orgDetail.org_type} />
            <FieldRow label="NPI" value={orgDetail.npi} />
            <FieldRow label="Tax ID" value={orgDetail.tin} />
          </div>
        </div>

        {/* Address */}
        <div>
          <h4 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-3">Address</h4>
          <div className="space-y-0">
            <FieldRow label="Street" value={editData.address || orgDetail.address} editable isEditing={isEditing} onEdit={(v) => setEditData({ ...editData, address: v })} />
            <FieldRow label="City" value={editData.city || orgDetail.city} editable isEditing={isEditing} onEdit={(v) => setEditData({ ...editData, city: v })} />
            <FieldRow label="State" value={editData.state || orgDetail.state} editable isEditing={isEditing} onEdit={(v) => setEditData({ ...editData, state: v.toUpperCase() })} type="state" />
            <FieldRow label="ZIP" value={editData.zip || orgDetail.zip} editable isEditing={isEditing} onEdit={(v) => setEditData({ ...editData, zip: v })} />
          </div>
        </div>

        {/* Contact Information */}
        <div>
          <h4 className="text-sm font-semibold text-gray-600 uppercase tracking-wide mb-3">Contact Information</h4>
          <div className="space-y-0">
            <FieldRow label="Phone" value={editData.phone || orgDetail.phone} editable isEditing={isEditing} onEdit={(v) => setEditData({ ...editData, phone: v })} type="tel" />
            <FieldRow label="Email" value={editData.contact_email || orgDetail.contact_email} editable isEditing={isEditing} onEdit={(v) => setEditData({ ...editData, contact_email: v })} type="email" />
            <FieldRow label="Contact Name" value={editData.contact_name || orgDetail.contact_name} editable isEditing={isEditing} onEdit={(v) => setEditData({ ...editData, contact_name: v })} />
            <div className="flex items-center gap-4 py-3">
              <label className="text-base font-bold" style={{ color: PINK, minWidth: '160px' }}>
                Notification:
              </label>
              {isEditing ? (
                <select
                  value={editData.contact_email ? 'email' : 'portal'}
                  onChange={(e) => setEditData({ ...editData, contact_email: e.target.value === 'email' ? 'email' : undefined })}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                >
                  <option value="email">Email</option>
                  <option value="portal">Portal Upload</option>
                </select>
              ) : (
                <span className="text-sm text-gray-900 flex-1">{orgDetail.contact_email ? 'Email' : 'Portal Upload'}</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {isEditing && (
        <div className="flex gap-3 pt-4 border-t border-gray-200">
          <button
            onClick={() => setIsEditing(false)}
            className="flex-1 px-4 py-2 bg-gray-600 text-white font-semibold rounded-lg hover:bg-gray-700 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onSave()}
            disabled={saving}
            className="flex-1 px-4 py-2 text-white font-semibold rounded-lg hover:opacity-90 transition-colors inline-flex items-center justify-center gap-2 disabled:opacity-60"
            style={{ backgroundColor: PINK }}
          >
            <Save className="w-4 h-4" />
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      )}
    </div>
  )
}

// ── Plans Tab ──
function PlansTab({
  orgId,
  mockContracts,
  onDownloadContract,
  orgDetail,
}: {
  orgId: string
  mockContracts: Array<{ id: string; name: string; type: string; year: number }>
  onDownloadContract: (id: string) => void
  orgDetail: OrgDetail
}) {
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null)
  const [modalType, setModalType] = useState<'contract' | 'fee-schedule' | null>(null)

  const plans = [
    { id: 'ma', label: 'MA (Medicare Advantage)', description: 'HMO & PPO Medicare Advantage plans' },
    { id: 'ppo', label: 'PPO', description: 'Preferred Provider Organization plans' },
    { id: 'hmo', label: 'HMO', description: 'Health Maintenance Organization plans' },
    { id: 'medicaid', label: 'Medicaid', description: 'State Medicaid programs' },
  ]

  const getPlanFeeSchedules = (planId: string) => {
    return orgDetail.fee_schedules.filter((fs) => fs.lob?.toLowerCase() === planId)
  }

  const getPlanContracts = (planId: string) => {
    return mockContracts.filter((c) => c.type?.toLowerCase() === planId)
  }

  return (
    <div className="space-y-4">
      <p className="text-gray-600 mb-6">Select a plan to view its contract and fee schedule:</p>

      {/* Plans List */}
      <div className="space-y-3">
        {plans.map((plan) => (
          <div
            key={plan.id}
            className="border border-gray-200 rounded-lg p-4 hover:border-gray-300 hover:shadow-sm transition-all"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <h4 className="font-semibold text-gray-900">{plan.label}</h4>
                <p className="text-sm text-gray-600 mt-1">{plan.description}</p>
              </div>
              <div className="flex gap-2 ml-4">
                <button
                  onClick={() => {
                    setSelectedPlan(plan.id)
                    setModalType('contract')
                  }}
                  className="px-3 py-2 text-sm font-medium text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                >
                  Contract
                </button>
                <button
                  onClick={() => {
                    setSelectedPlan(plan.id)
                    setModalType('fee-schedule')
                  }}
                  className="px-3 py-2 text-sm font-medium text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                >
                  Fee Schedule
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Modals */}
      {selectedPlan && modalType === 'contract' && (
        <ContractModal
          planId={selectedPlan}
          planLabel={plans.find((p) => p.id === selectedPlan)?.label || ''}
          contracts={getPlanContracts(selectedPlan)}
          onDownload={onDownloadContract}
          onClose={() => {
            setSelectedPlan(null)
            setModalType(null)
          }}
        />
      )}

      {selectedPlan && modalType === 'fee-schedule' && (
        <FeeScheduleModal
          planId={selectedPlan}
          planLabel={plans.find((p) => p.id === selectedPlan)?.label || ''}
          feeSchedules={getPlanFeeSchedules(selectedPlan)}
          onClose={() => {
            setSelectedPlan(null)
            setModalType(null)
          }}
        />
      )}
    </div>
  )
}

// ── Contract Modal ──
function ContractModal({
  planId,
  planLabel,
  contracts,
  onDownload,
  onClose,
}: {
  planId: string
  planLabel: string
  contracts: Array<{ id: string; name: string; type: string; year: number }>
  onDownload: (id: string) => void
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg max-w-2xl w-full max-h-96 overflow-auto shadow-lg">
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">Contracts - {planLabel}</h3>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 text-2xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="p-6">
          {contracts.length === 0 ? (
            <p className="text-gray-500">No contracts available for this plan</p>
          ) : (
            <div className="space-y-3">
              {contracts.map((contract) => (
                <div
                  key={contract.id}
                  className="border border-gray-200 rounded-lg p-4 flex items-center justify-between hover:bg-gray-50"
                >
                  <div className="flex items-center gap-3">
                    <FileText className="w-5 h-5 text-gray-400" />
                    <div>
                      <p className="font-medium text-gray-900">{contract.name}</p>
                      <p className="text-sm text-gray-500">{contract.year}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => onDownload(contract.id)}
                    className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                    title="Download contract"
                  >
                    <Download className="w-5 h-5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Fee Schedule Modal ──
function FeeScheduleModal({
  planId,
  planLabel,
  feeSchedules,
  onClose,
}: {
  planId: string
  planLabel: string
  feeSchedules: FeeScheduleRow[]
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg max-w-4xl w-full max-h-96 overflow-auto shadow-lg">
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">Fee Schedule - {planLabel}</h3>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 text-2xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="p-6">
          {feeSchedules.length === 0 ? (
            <p className="text-gray-500">No fee schedules configured for this plan</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="px-4 py-2 text-left font-semibold text-gray-700">CPT Code</th>
                    <th className="px-4 py-2 text-left font-semibold text-gray-700">Description</th>
                    <th className="px-4 py-2 text-left font-semibold text-gray-700">Effective Date</th>
                    <th className="px-4 py-2 text-right font-semibold text-gray-700">Base Rate</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {feeSchedules.map((row) => (
                    <tr key={row.fee_schedule_id} className="hover:bg-gray-50">
                      <td className="px-4 py-2 font-mono text-gray-900">{row.cpt_code}</td>
                      <td className="px-4 py-2 text-gray-700">{row.cpt_description || '—'}</td>
                      <td className="px-4 py-2 text-gray-700">{row.effective_date}</td>
                      <td className="px-4 py-2 text-right font-mono text-gray-900">
                        ${row.base_rate.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
