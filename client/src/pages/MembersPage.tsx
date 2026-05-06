import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Users, Plus, Pencil, Trash2, Search, X, AlertTriangle } from 'lucide-react'
import api from '../services/api'

interface MemberRecord {
  member_id: string
  member_number: string
  first_name: string
  last_name: string
  date_of_birth: string
  lob: string
  coverage_effective_date: string
  coverage_termination_date: string | null
  created_at: string
  updated_at: string
}

interface MemberListResponse {
  total: number
  items: MemberRecord[]
}

interface MemberForm {
  member_number: string
  first_name: string
  last_name: string
  date_of_birth: string
  lob: string
  coverage_effective_date: string
  coverage_termination_date: string
}

const LOBS = ['MA', 'PPO', 'Medicaid']

const EMPTY_FORM: MemberForm = {
  member_number: '',
  first_name: '',
  last_name: '',
  date_of_birth: '',
  lob: 'MA',
  coverage_effective_date: '',
  coverage_termination_date: '',
}

function coverageStatus(member: MemberRecord): { label: string; cls: string } {
  const today = new Date().toISOString().slice(0, 10)
  if (member.coverage_effective_date > today) {
    return { label: 'Not Yet Active', cls: 'bg-amber-100 text-amber-700 border border-amber-200' }
  }
  if (member.coverage_termination_date && member.coverage_termination_date <= today) {
    return { label: 'Terminated', cls: 'bg-red-100 text-red-700 border border-red-200' }
  }
  return { label: 'Active', cls: 'bg-green-100 text-green-700 border border-green-200' }
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function MembersPage() {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [lobFilter, setLobFilter] = useState('')
  const [modal, setModal] = useState<'add' | 'edit' | null>(null)
  const [editing, setEditing] = useState<MemberRecord | null>(null)
  const [form, setForm] = useState<MemberForm>(EMPTY_FORM)
  const [deleteTarget, setDeleteTarget] = useState<MemberRecord | null>(null)
  const [formError, setFormError] = useState('')

  const PAGE_SIZE = 20

  const { data, isLoading } = useQuery<MemberListResponse>({
    queryKey: ['members', page, search, lobFilter],
    queryFn: async () => {
      const params: Record<string, string | number> = { page, page_size: PAGE_SIZE }
      if (search) params.search = search
      if (lobFilter) params.lob = lobFilter
      const res = await api.get<MemberListResponse>('/members', { params })
      return res.data
    },
    staleTime: 30_000,
  })

  const createMutation = useMutation({
    mutationFn: (body: MemberForm) =>
      api.post<MemberRecord>('/members', {
        ...body,
        coverage_termination_date: body.coverage_termination_date || null,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['members'] }); closeModal() },
    onError: (e: any) => setFormError(e?.response?.data?.detail ?? 'Failed to create member'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: MemberForm }) =>
      api.put<MemberRecord>(`/members/${id}`, {
        ...body,
        coverage_termination_date: body.coverage_termination_date || null,
      }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['members'] }); closeModal() },
    onError: (e: any) => setFormError(e?.response?.data?.detail ?? 'Failed to update member'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/members/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['members'] }); setDeleteTarget(null) },
  })

  function openAdd() {
    setForm(EMPTY_FORM)
    setFormError('')
    setEditing(null)
    setModal('add')
  }

  function openEdit(m: MemberRecord) {
    setForm({
      member_number: m.member_number,
      first_name: m.first_name,
      last_name: m.last_name,
      date_of_birth: m.date_of_birth,
      lob: m.lob,
      coverage_effective_date: m.coverage_effective_date,
      coverage_termination_date: m.coverage_termination_date ?? '',
    })
    setFormError('')
    setEditing(m)
    setModal('edit')
  }

  function closeModal() {
    setModal(null)
    setEditing(null)
    setFormError('')
  }

  function handleSubmit() {
    if (!form.member_number || !form.first_name || !form.last_name || !form.date_of_birth || !form.coverage_effective_date) {
      setFormError('All fields except Plan Expiry are required')
      return
    }
    setFormError('')
    if (modal === 'add') {
      createMutation.mutate(form)
    } else if (editing) {
      updateMutation.mutate({ id: editing.member_id, body: form })
    }
  }

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div className="flex flex-col gap-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Members</h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage member eligibility records and coverage dates.
          </p>
        </div>
        <button
          onClick={openAdd}
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-[#FE017D] text-white
                     text-sm font-semibold rounded-lg hover:bg-[#e5006f] transition-colors shadow-sm"
        >
          <Plus className="w-4 h-4" />
          Add Member
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
          <input
            type="text"
            placeholder="Search by name or member #…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            className="w-full pl-8 pr-3 py-2 text-sm border border-gray-200 rounded-lg
                       focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]
                       bg-gray-50 text-gray-800 transition-colors"
          />
        </div>

        <select
          value={lobFilter}
          onChange={(e) => { setLobFilter(e.target.value); setPage(1) }}
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg bg-gray-50
                     text-gray-700 focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30"
        >
          <option value="">All LOBs</option>
          {LOBS.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>

        <span className="text-xs text-gray-400 ml-auto">{total} member{total !== 1 ? 's' : ''}</span>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Member #</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Name</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">DOB</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">LOB</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Plan Start</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Plan Expiry</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading && (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-sm text-gray-400">Loading…</td>
              </tr>
            )}
            {!isLoading && items.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-sm text-gray-400">
                  <Users className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                  No members found
                </td>
              </tr>
            )}
            {items.map((m) => {
              const status = coverageStatus(m)
              return (
                <tr key={m.member_id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">{m.member_number}</td>
                  <td className="px-4 py-3 font-medium text-gray-900">{m.first_name} {m.last_name}</td>
                  <td className="px-4 py-3 text-gray-600">{formatDate(m.date_of_birth)}</td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700">
                      {m.lob}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{formatDate(m.coverage_effective_date)}</td>
                  <td className="px-4 py-3 text-gray-600">{formatDate(m.coverage_termination_date)}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${status.cls}`}>
                      {status.label}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => openEdit(m)}
                        className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
                        title="Edit"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => setDeleteTarget(m)}
                        className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                        title="Delete"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between">
            <span className="text-xs text-gray-500">
              Page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
                className="px-3 py-1.5 text-xs border border-gray-200 rounded-lg text-gray-600
                           hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Previous
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1.5 text-xs border border-gray-200 rounded-lg text-gray-600
                           hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Add / Edit Modal */}
      {modal && (
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
          onClick={(e) => { if (e.target === e.currentTarget) closeModal() }}
        >
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <h2 className="text-base font-bold text-gray-900">
                {modal === 'add' ? 'Add Member' : 'Edit Member'}
              </h2>
              <button
                onClick={closeModal}
                className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="px-6 py-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <Field label="First Name">
                  <input
                    type="text"
                    value={form.first_name}
                    onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                    className={inputCls}
                  />
                </Field>
                <Field label="Last Name">
                  <input
                    type="text"
                    value={form.last_name}
                    onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                    className={inputCls}
                  />
                </Field>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <Field label="Member Number">
                  <input
                    type="text"
                    value={form.member_number}
                    onChange={(e) => setForm({ ...form, member_number: e.target.value })}
                    className={`${inputCls} font-mono`}
                    placeholder="MBR-XXXX"
                  />
                </Field>
                <Field label="Date of Birth">
                  <input
                    type="date"
                    value={form.date_of_birth}
                    onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })}
                    className={inputCls}
                  />
                </Field>
              </div>

              <Field label="Line of Business">
                <select
                  value={form.lob}
                  onChange={(e) => setForm({ ...form, lob: e.target.value })}
                  className={inputCls}
                >
                  {LOBS.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </Field>

              <div className="grid grid-cols-2 gap-4">
                <Field label="Plan Start Date">
                  <input
                    type="date"
                    value={form.coverage_effective_date}
                    onChange={(e) => setForm({ ...form, coverage_effective_date: e.target.value })}
                    className={inputCls}
                  />
                </Field>
                <Field label="Plan Expiry Date">
                  <input
                    type="date"
                    value={form.coverage_termination_date}
                    onChange={(e) => setForm({ ...form, coverage_termination_date: e.target.value })}
                    className={inputCls}
                    placeholder="Leave blank for active"
                  />
                </Field>
              </div>

              {formError && (
                <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5">
                  <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                  <p className="text-xs text-red-700">{formError}</p>
                </div>
              )}
            </div>

            <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-end gap-3 bg-gray-50">
              <button
                onClick={closeModal}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={createMutation.isPending || updateMutation.isPending}
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-[#FE017D] text-white
                           text-sm font-semibold rounded-lg hover:bg-[#e5006f]
                           disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {(createMutation.isPending || updateMutation.isPending) ? (
                  <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : null}
                {modal === 'add' ? 'Add Member' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation */}
      {deleteTarget && (
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
          onClick={(e) => { if (e.target === e.currentTarget) setDeleteTarget(null) }}
        >
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden">
            <div className="px-6 py-5">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0">
                  <Trash2 className="w-5 h-5 text-red-600" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-gray-900">Delete Member</h3>
                  <p className="text-sm text-gray-500">This action cannot be undone.</p>
                </div>
              </div>
              <p className="text-sm text-gray-700">
                Remove <span className="font-semibold">{deleteTarget.first_name} {deleteTarget.last_name}</span> ({deleteTarget.member_number}) from the system?
              </p>
            </div>
            <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-end gap-3 bg-gray-50">
              <button
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteTarget.member_id)}
                disabled={deleteMutation.isPending}
                className="px-5 py-2.5 bg-red-600 text-white text-sm font-semibold rounded-lg
                           hover:bg-red-700 disabled:opacity-40 transition-colors"
              >
                {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const inputCls = `w-full px-3 py-2 text-sm border border-gray-200 rounded-lg bg-gray-50
  text-gray-800 focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]
  transition-colors`

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{label}</label>
      {children}
    </div>
  )
}
