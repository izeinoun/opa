import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Mail, Edit, Save, X, Plus, AlertCircle } from 'lucide-react'
import api from '../services/api'

interface ProviderOrg {
  provider_org_id: string
  name: string
  npi: string
  tin: string
  org_type: string
}

interface Playbook {
  playbook_id: string
  provider_org_id: string
  delivery_type: string
  status: string
  contact_email: string | null
  contact_name: string | null
  email_template_ref: string | null
}

interface ProviderWithPlaybook extends ProviderOrg {
  playbook?: Playbook
}

export default function ProvidersPage() {
  const [searchTerm, setSearchTerm] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingEmail, setEditingEmail] = useState('')
  const [editingName, setEditingName] = useState('')
  const [saveMessage, setSaveMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const queryClient = useQueryClient()

  // Fetch all providers
  const { data: providers = [], isLoading, error } = useQuery({
    queryKey: ['providers'],
    queryFn: async () => {
      const res = await api.get<ProviderOrg[]>('/fee-schedules')
      // Fetch playbooks for each provider
      const withPlaybooks = await Promise.all(
        res.data.map(async (org) => {
          try {
            const pbRes = await api.get<Playbook>(`/fee-schedules/${org.provider_org_id}/playbook`)
            return { ...org, playbook: pbRes.data }
          } catch {
            return { ...org }
          }
        })
      )
      return withPlaybooks
    },
  })

  // Save playbook mutation
  const saveMutation = useMutation({
    mutationFn: async (orgId: string) => {
      const payload = {
        delivery_type: 'email',
        status: 'active',
        contact_email: editingEmail,
        contact_name: editingName,
        email_template_ref: 'template_fxz7i4o',
      }
      return await api.put(`/fee-schedules/${orgId}/playbook`, payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] })
      setEditingId(null)
      setSaveMessage({ type: 'success', text: 'Provider email saved successfully' })
      setTimeout(() => setSaveMessage(null), 3000)
    },
    onError: (error: any) => {
      setSaveMessage({ type: 'error', text: error.response?.data?.detail || 'Failed to save' })
    },
  })

  const handleEdit = (org: ProviderWithPlaybook) => {
    setEditingId(org.provider_org_id)
    setEditingEmail(org.playbook?.contact_email || '')
    setEditingName(org.playbook?.contact_name || '')
  }

  const handleSave = () => {
    if (!editingEmail) {
      setSaveMessage({ type: 'error', text: 'Email address is required' })
      return
    }
    saveMutation.mutate(editingId!)
  }

  const filteredProviders = providers.filter(
    (p) =>
      p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.npi.includes(searchTerm) ||
      p.tin.includes(searchTerm)
  )

  if (isLoading) return <div className="p-6">Loading providers...</div>
  if (error) return <div className="p-6 text-red-600">Error loading providers</div>

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Providers</h1>
        <p className="text-gray-600">Configure email addresses for provider delivery notifications</p>
      </div>

      {/* Search */}
      <div className="mb-6">
        <input
          type="text"
          placeholder="Search by name, NPI, or TIN..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
      </div>

      {/* Messages */}
      {saveMessage && (
        <div
          className={`mb-6 p-4 rounded-lg flex items-center gap-2 ${
            saveMessage.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'
          }`}
        >
          <AlertCircle className="w-4 h-4" />
          {saveMessage.text}
        </div>
      )}

      {/* Providers Table */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">Provider Organization</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">NPI / TIN</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">Contact Email</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700">Status</th>
              <th className="px-6 py-3 text-center text-sm font-semibold text-gray-700">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {filteredProviders.map((provider) => (
              <tr key={provider.provider_org_id} className="hover:bg-gray-50">
                <td className="px-6 py-4">
                  <div className="font-medium text-gray-900">{provider.name}</div>
                  <div className="text-sm text-gray-500">{provider.org_type}</div>
                </td>
                <td className="px-6 py-4 text-sm font-mono text-gray-600">
                  <div>{provider.npi}</div>
                  <div className="text-gray-500">{provider.tin}</div>
                </td>
                <td className="px-6 py-4">
                  {editingId === provider.provider_org_id ? (
                    <div className="space-y-2">
                      <input
                        type="email"
                        value={editingEmail}
                        onChange={(e) => setEditingEmail(e.target.value)}
                        placeholder="billing@provider.com"
                        className="w-full px-3 py-2 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                      <input
                        type="text"
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        placeholder="Contact Name"
                        className="w-full px-3 py-2 border border-gray-300 rounded text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      />
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <Mail className="w-4 h-4 text-gray-400" />
                      <span className="text-gray-900">
                        {'playbook' in provider && provider.playbook?.contact_email ? (
                          provider.playbook.contact_email
                        ) : (
                          <span className="text-gray-400 italic">Not configured</span>
                        )}
                      </span>
                    </div>
                  )}
                </td>
                <td className="px-6 py-4 text-sm">
                  {editingId === provider.provider_org_id ? (
                    <span className="px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-700">Editing</span>
                  ) : 'playbook' in provider && provider.playbook?.status === 'active' ? (
                    <span className="px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700">Active</span>
                  ) : (
                    <span className="px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-700">
                      {'playbook' in provider ? provider.playbook?.status || 'Draft' : 'Not configured'}
                    </span>
                  )}
                </td>
                <td className="px-6 py-4 text-center">
                  {editingId === provider.provider_org_id ? (
                    <div className="flex items-center justify-center gap-2">
                      <button
                        onClick={handleSave}
                        disabled={saveMutation.isPending}
                        className="inline-flex items-center gap-1 px-3 py-1.5 bg-green-600 text-white text-sm rounded hover:bg-green-700 disabled:bg-gray-400 transition-colors"
                      >
                        <Save className="w-4 h-4" />
                        Save
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        disabled={saveMutation.isPending}
                        className="inline-flex items-center gap-1 px-3 py-1.5 bg-gray-300 text-gray-700 text-sm rounded hover:bg-gray-400 disabled:bg-gray-200 transition-colors"
                      >
                        <X className="w-4 h-4" />
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => handleEdit(provider)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors"
                    >
                      <Edit className="w-4 h-4" />
                      Edit
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filteredProviders.length === 0 && (
          <div className="px-6 py-12 text-center text-gray-500">
            No providers found matching your search
          </div>
        )}
      </div>

      {/* Summary */}
      <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-800">
        <p className="font-semibold mb-2">📧 Email Configuration Summary</p>
        <p>
          Configured: <strong>{filteredProviders.filter((p) => 'playbook' in p && p.playbook?.contact_email).length}</strong> /{' '}
          <strong>{filteredProviders.length}</strong>
        </p>
      </div>
    </div>
  )
}
