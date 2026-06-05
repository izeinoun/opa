import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, XCircle } from 'lucide-react'
import api from '../../../services/api'
import type { User } from '../../../types'

const ROLE_STYLE: Record<string, string> = {
  admin:      'bg-[#FE017D]/10 text-[#FE017D]',
  supervisor: 'bg-purple-100 text-purple-700',
  analyst:    'bg-gray-100 text-gray-600',
}

export default function UsersPanel() {
  const qc = useQueryClient()

  const { data: users = [], isLoading } = useQuery<User[]>({
    queryKey: ['admin', 'users'],
    queryFn: async () => (await api.get<User[]>('/admin/users')).data,
  })

  const toggleMutation = useMutation({
    mutationFn: async ({ userId, isActive }: { userId: string; isActive: boolean }) =>
      (await api.patch<User>(`/admin/users/${userId}`, { is_active: isActive })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  })

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      {isLoading ? (
        <div className="p-5 space-y-2 animate-pulse">
          {[...Array(6)].map((_, i) => <div key={i} className="h-11 bg-gray-100 rounded-lg" />)}
        </div>
      ) : (
        <table className="min-w-full divide-y divide-gray-100">
          <thead className="bg-gray-50">
            <tr>
              {['Name', 'Username', 'Email', 'Role', 'Status', 'Action'].map(h => (
                <th key={h} className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {users.map(u => (
              <tr key={u.id} className={`hover:bg-gray-50 transition-colors ${!u.is_active ? 'opacity-50' : ''}`}>
                <td className="px-5 py-3.5 text-sm font-medium text-gray-900">{u.full_name}</td>
                <td className="px-5 py-3.5 text-sm font-mono text-gray-600">{u.username}</td>
                <td className="px-5 py-3.5 text-sm text-gray-600">{u.email}</td>
                <td className="px-5 py-3.5">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${ROLE_STYLE[u.role] ?? 'bg-gray-100 text-gray-600'}`}>
                    {u.role}
                  </span>
                </td>
                <td className="px-5 py-3.5">
                  {u.is_active
                    ? <span className="inline-flex items-center gap-1 text-xs text-green-700"><CheckCircle className="w-3.5 h-3.5" /> Active</span>
                    : <span className="inline-flex items-center gap-1 text-xs text-gray-400"><XCircle className="w-3.5 h-3.5" /> Inactive</span>
                  }
                </td>
                <td className="px-5 py-3.5">
                  <button
                    onClick={() => toggleMutation.mutate({ userId: u.id, isActive: !u.is_active })}
                    disabled={toggleMutation.isPending}
                    className={`text-xs px-2.5 py-1 rounded-lg border transition-colors ${
                      u.is_active
                        ? 'border-red-200 text-red-600 hover:bg-red-50'
                        : 'border-green-200 text-green-600 hover:bg-green-50'
                    }`}
                  >
                    {u.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
