import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Search } from 'lucide-react'
import { useState } from 'react'
import api from '../services/api'

interface ProviderOrg {
  provider_org_id: string
  name: string
  npi: string
  tin: string
  org_type: string
  address?: string
  city?: string
  state?: string
  billing_variance_score?: number
  is_active?: boolean
}

export default function ProvidersPage() {
  const navigate = useNavigate()
  const [searchTerm, setSearchTerm] = useState('')

  const { data: providers = [], isLoading, error } = useQuery({
    queryKey: ['providers'],
    queryFn: async () => {
      const res = await api.get<ProviderOrg[]>('/fee-schedules')
      return res.data
    },
  })

  const filteredProviders = providers.filter(
    (p) =>
      p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      p.npi.includes(searchTerm) ||
      p.tin.includes(searchTerm)
  )

  if (isLoading) {
    return (
      <div className="max-w-6xl mx-auto p-6">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-1/4 mb-6"></div>
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-16 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-6xl mx-auto p-6">
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-800">
          Failed to load providers
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto p-6">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Providers</h1>
        <p className="text-gray-600">Manage provider information, fee schedules, contracts, and delivery settings</p>
      </div>

      {/* Search */}
      <div className="mb-6">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
          <input
            type="text"
            placeholder="Search by name, NPI, or TIN..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
      </div>

      {/* Provider List */}
      <div className="space-y-2">
        {filteredProviders.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <p>No providers found matching your search</p>
          </div>
        ) : (
          filteredProviders.map((provider) => (
            <button
              key={provider.provider_org_id}
              onClick={() => navigate(`/providers/${provider.provider_org_id}`)}
              className="w-full text-left bg-white border border-gray-200 rounded-lg hover:border-gray-300 hover:shadow-md transition-all p-4 group"
            >
              <div className="flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-lg font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
                      {provider.name}
                    </h3>
                    {provider.is_active ? (
                      <span className="px-2 py-1 text-xs font-medium bg-green-100 text-green-700 rounded-full">
                        Active
                      </span>
                    ) : (
                      <span className="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-600 rounded-full">
                        Inactive
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-4 text-sm text-gray-600">
                    <div>
                      <span className="text-gray-500">NPI:</span>
                      <span className="ml-2 font-mono text-gray-900">{provider.npi}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">TIN:</span>
                      <span className="ml-2 font-mono text-gray-900">{provider.tin}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Type:</span>
                      <span className="ml-2 text-gray-900">{provider.org_type}</span>
                    </div>
                    {provider.billing_variance_score !== undefined && (
                      <div>
                        <span className="text-gray-500">Risk Score:</span>
                        <span className="ml-2 text-gray-900">
                          {(provider.billing_variance_score * 100).toFixed(0)}%
                        </span>
                      </div>
                    )}
                  </div>
                </div>
                <ChevronRight className="w-5 h-5 text-gray-400 group-hover:text-blue-600 transition-colors flex-shrink-0 ml-4" />
              </div>
            </button>
          ))
        )}
      </div>

      {/* Summary */}
      {filteredProviders.length > 0 && (
        <div className="mt-8 p-4 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-800">
          <p>
            Showing <strong>{filteredProviders.length}</strong> of <strong>{providers.length}</strong> providers
          </p>
        </div>
      )}
    </div>
  )
}
