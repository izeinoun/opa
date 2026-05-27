import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Phone, Mail, FileText, Users, Globe, ArrowDownLeft, ArrowUpRight, Plus } from 'lucide-react'
import api from '../../services/api'
import { formatDate } from '../../utils/dateUtils'

interface Contact {
  id: string
  contact_date: string
  method: string
  direction: 'outbound' | 'inbound'
  participant_name?: string | null
  summary: string
  logged_by_full_name?: string | null
  created_at: string
}

const METHOD_ICON: Record<string, any> = {
  phone: Phone, email: Mail, letter: FileText, in_person: Users, portal: Globe,
}
const METHOD_LABEL: Record<string, string> = {
  phone: 'Phone', email: 'Email', letter: 'Letter', in_person: 'In person', portal: 'Portal',
}

export default function ContactLog({ caseId }: { caseId: number }) {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [contactDate, setContactDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [method, setMethod] = useState('phone')
  const [direction, setDirection] = useState<'outbound' | 'inbound'>('outbound')
  const [participant, setParticipant] = useState('')
  const [summary, setSummary] = useState('')

  const { data: items = [], isLoading } = useQuery<Contact[]>({
    queryKey: ['contacts', caseId],
    queryFn: async () => (await api.get<Contact[]>(`/cases/${caseId}/contacts`)).data,
  })

  const mut = useMutation({
    mutationFn: async () => api.post(`/cases/${caseId}/contacts`, {
      contact_date: contactDate, method, direction,
      participant_name: participant.trim() || null,
      summary: summary.trim(),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contacts', caseId] })
      queryClient.invalidateQueries({ queryKey: ['case', caseId] })
      setShowForm(false)
      setParticipant(''); setSummary('')
    },
  })

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Phone className="w-4 h-4 text-gray-500" />
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Contact Log</h3>
          {items.length > 0 && <span className="text-xs text-gray-400">({items.length})</span>}
        </div>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-50 rounded transition-colors"
        >
          <Plus className="w-3 h-3" /> Log contact
        </button>
      </div>

      {showForm && (
        <div className="bg-gray-50 border border-gray-100 rounded-lg p-3 mb-3 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[11px] font-semibold text-gray-600 block mb-0.5">Date</label>
              <input type="date" value={contactDate} onChange={(e) => setContactDate(e.target.value)}
                className="w-full px-2 py-1 text-xs border border-gray-200 rounded" />
            </div>
            <div>
              <label className="text-[11px] font-semibold text-gray-600 block mb-0.5">Direction</label>
              <select value={direction} onChange={(e) => setDirection(e.target.value as any)}
                className="w-full px-2 py-1 text-xs border border-gray-200 rounded bg-white">
                <option value="outbound">Outbound (we contacted them)</option>
                <option value="inbound">Inbound (they contacted us)</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] font-semibold text-gray-600 block mb-0.5">Method</label>
              <select value={method} onChange={(e) => setMethod(e.target.value)}
                className="w-full px-2 py-1 text-xs border border-gray-200 rounded bg-white">
                {Object.entries(METHOD_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[11px] font-semibold text-gray-600 block mb-0.5">Participant <span className="font-normal text-gray-400">(optional)</span></label>
              <input type="text" value={participant} onChange={(e) => setParticipant(e.target.value)}
                placeholder="Name or role" className="w-full px-2 py-1 text-xs border border-gray-200 rounded" />
            </div>
          </div>
          <div>
            <label className="text-[11px] font-semibold text-gray-600 block mb-0.5">Summary</label>
            <textarea value={summary} onChange={(e) => setSummary(e.target.value)}
              rows={2} placeholder="What was discussed or attempted…"
              className="w-full px-2 py-1 text-xs border border-gray-200 rounded resize-none" />
          </div>
          {mut.isError && (
            <p className="text-xs text-red-600">{(mut.error as any)?.response?.data?.detail ?? 'Failed'}</p>
          )}
          <div className="flex justify-end gap-2">
            <button onClick={() => setShowForm(false)}
              className="px-3 py-1 text-xs text-gray-700 bg-white border border-gray-200 rounded hover:bg-gray-50">
              Cancel
            </button>
            <button onClick={() => mut.mutate()} disabled={!summary.trim() || mut.isPending}
              className="px-3 py-1 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded disabled:bg-gray-200">
              {mut.isPending ? 'Saving…' : 'Add'}
            </button>
          </div>
        </div>
      )}

      {isLoading ? (
        <p className="text-xs text-gray-400 italic">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-xs text-gray-400 italic">No contact attempts logged yet.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((c) => {
            const Icon = METHOD_ICON[c.method] ?? FileText
            const DirIcon = c.direction === 'outbound' ? ArrowUpRight : ArrowDownLeft
            const dirColor = c.direction === 'outbound' ? 'text-blue-600' : 'text-green-600'
            return (
              <li key={c.id} className="border border-gray-100 rounded-lg p-2.5">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0">
                    <Icon className="w-3 h-3 text-gray-600" />
                  </div>
                  <span className="text-sm font-semibold text-gray-800">{METHOD_LABEL[c.method] ?? c.method}</span>
                  <DirIcon className={`w-3.5 h-3.5 ${dirColor}`} />
                  <span className="text-xs text-gray-500">{c.contact_date}</span>
                  {c.participant_name && (
                    <span className="text-xs text-gray-500">· {c.participant_name}</span>
                  )}
                  <span className="ml-auto text-[11px] text-gray-400">
                    {c.logged_by_full_name ?? 'Unknown'} · {formatDate(c.created_at)}
                  </span>
                </div>
                <p className="text-sm text-gray-700 whitespace-pre-wrap">{c.summary}</p>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
