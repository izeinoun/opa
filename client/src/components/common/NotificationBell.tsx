import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell, CheckCheck, FileText, UserPlus, RefreshCw, ShieldCheck } from 'lucide-react'
import api from '../../services/api'
import { formatRelative } from '../../utils/dateUtils'

type NotificationKind =
  | 'case_assigned' | 'approval_requested' | 'approval_decided'
  | 'case_reopened' | 'note_mention'

interface NotificationItem {
  id: string
  kind: NotificationKind
  title: string
  body?: string | null
  link?: string | null
  case_id?: string | null
  case_number?: string | null
  case_sequence?: number | null
  actor?: { id: string; full_name: string; role: string } | null
  is_read: boolean
  created_at: string
}

const KIND_ICON: Record<NotificationKind, typeof Bell> = {
  case_assigned:      UserPlus,
  approval_requested: ShieldCheck,
  approval_decided:   ShieldCheck,
  case_reopened:      RefreshCw,
  note_mention:       FileText,
}

const KIND_TINT: Record<NotificationKind, string> = {
  case_assigned:      'text-blue-600 bg-blue-50',
  approval_requested: 'text-amber-600 bg-amber-50',
  approval_decided:   'text-green-600 bg-green-50',
  case_reopened:      'text-purple-600 bg-purple-50',
  note_mention:       'text-gray-600 bg-gray-50',
}

export default function NotificationBell() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const { data: countData } = useQuery({
    queryKey: ['notif-count'],
    queryFn: async () => (await api.get<{ unread: number }>('/notifications/count')).data,
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  })
  const unread = countData?.unread ?? 0

  const { data: items = [], isLoading } = useQuery<NotificationItem[]>({
    queryKey: ['notif-list'],
    queryFn: async () => (await api.get<NotificationItem[]>('/notifications?limit=15')).data,
    enabled: open,
  })

  const markReadMut = useMutation({
    mutationFn: async (id: string) => api.post(`/notifications/${id}/read`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notif-count'] })
      queryClient.invalidateQueries({ queryKey: ['notif-list'] })
    },
  })

  const markAllMut = useMutation({
    mutationFn: async () => api.post('/notifications/mark-all-read'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notif-count'] })
      queryClient.invalidateQueries({ queryKey: ['notif-list'] })
    },
  })

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const onItemClick = (n: NotificationItem) => {
    if (!n.is_read) markReadMut.mutate(n.id)
    setOpen(false)
    const target = n.link
      ?? (n.case_sequence != null ? `/cases/${n.case_sequence}` : null)
    if (target) navigate(target)
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative flex items-center justify-center w-9 h-9 rounded-lg border border-gray-200 hover:border-gray-300 hover:bg-gray-50 transition-colors"
        aria-label={`Notifications (${unread} unread)`}
      >
        <Bell className="w-4 h-4 text-gray-600" />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] rounded-full bg-[#FE017D] text-white text-[10px] font-bold flex items-center justify-center px-1">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-96 bg-white border border-gray-200 rounded-xl shadow-lg z-40 max-h-[32rem] overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
            <p className="text-sm font-bold text-gray-900">Notifications</p>
            {unread > 0 && (
              <button
                onClick={() => markAllMut.mutate()}
                disabled={markAllMut.isPending}
                className="text-xs text-indigo-600 hover:text-indigo-800 font-medium inline-flex items-center gap-1"
              >
                <CheckCheck className="w-3 h-3" /> Mark all read
              </button>
            )}
          </div>

          <div className="overflow-y-auto flex-1">
            {isLoading ? (
              <p className="px-4 py-6 text-xs text-gray-400 text-center">Loading…</p>
            ) : items.length === 0 ? (
              <p className="px-4 py-6 text-xs text-gray-400 text-center">No notifications yet.</p>
            ) : (
              <ul className="divide-y divide-gray-100">
                {items.map((n) => {
                  const Icon = KIND_ICON[n.kind] ?? Bell
                  const tint = KIND_TINT[n.kind] ?? 'text-gray-600 bg-gray-50'
                  return (
                    <li key={n.id}>
                      <button
                        onClick={() => onItemClick(n)}
                        className={`w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors flex gap-3 ${
                          !n.is_read ? 'bg-indigo-50/40' : ''
                        }`}
                      >
                        <div className={`w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center ${tint}`}>
                          <Icon className="w-3.5 h-3.5" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-baseline justify-between gap-2">
                            <p className={`text-sm truncate ${!n.is_read ? 'font-semibold text-gray-900' : 'font-medium text-gray-700'}`}>
                              {n.title}
                            </p>
                            <span className="text-[11px] text-gray-400 flex-shrink-0">
                              {formatRelative(n.created_at)}
                            </span>
                          </div>
                          {n.body && (
                            <p className="text-xs text-gray-500 truncate mt-0.5">{n.body}</p>
                          )}
                          {n.actor && (
                            <p className="text-[11px] text-gray-400 mt-0.5">by {n.actor.full_name}</p>
                          )}
                        </div>
                        {!n.is_read && (
                          <span className="w-2 h-2 rounded-full bg-indigo-500 flex-shrink-0 mt-2" />
                        )}
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
