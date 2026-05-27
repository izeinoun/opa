import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, Send, AtSign } from 'lucide-react'
import api from '../../services/api'
import { formatDate } from '../../utils/dateUtils'
import { useCurrentUser } from '../../hooks/useCurrentUser'
import type { CaseNote, User, UserRole } from '../../types'

const MENTION_RE = /@([a-z][a-z0-9._-]{1,30})/gi

function renderWithMentions(body: string): React.ReactNode {
  const parts: React.ReactNode[] = []
  let lastIdx = 0
  let m: RegExpExecArray | null
  MENTION_RE.lastIndex = 0
  while ((m = MENTION_RE.exec(body)) !== null) {
    if (m.index > lastIdx) parts.push(body.slice(lastIdx, m.index))
    parts.push(
      <span key={`m-${m.index}`} className="text-indigo-600 font-medium">@{m[1]}</span>
    )
    lastIdx = m.index + m[0].length
  }
  if (lastIdx < body.length) parts.push(body.slice(lastIdx))
  return parts
}


const ROLE_PILL: Record<UserRole, string> = {
  supervisor: 'bg-purple-100 text-purple-700',
  analyst:    'bg-blue-100 text-blue-700',
  admin:      'bg-[#FE017D]/10 text-[#FE017D]',
  system:     'bg-gray-100 text-gray-600',
}

// Match "@prefix" being typed at the cursor: an @ that's at start-of-string
// or after whitespace/punctuation, followed by 0+ chars of the username alphabet.
const MENTION_TRIGGER_RE = /(?:^|[\s(,;])@([a-zA-Z0-9._-]*)$/

interface MentionContext {
  prefix: string         // chars typed after @ so far
  startIdx: number       // index of the @ in the textarea value
}

function detectMention(value: string, caret: number): MentionContext | null {
  const before = value.slice(0, caret)
  const match = before.match(MENTION_TRIGGER_RE)
  if (!match) return null
  return {
    prefix: match[1] ?? '',
    startIdx: before.length - (match[1]?.length ?? 0) - 1, // -1 for the '@' itself
  }
}

export default function CaseNotes({ caseId }: { caseId: number }) {
  const queryClient = useQueryClient()
  const { currentUser, users } = useCurrentUser()
  const [draft, setDraft] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  // Mention autocomplete state
  const [mention, setMention] = useState<MentionContext | null>(null)
  const [highlightIdx, setHighlightIdx] = useState(0)

  const mentionableUsers: User[] = users
    .filter((u) =>
      u.is_active &&
      u.role !== 'system' &&
      u.id !== currentUser?.id  // don't suggest self
    )

  const matches = mention === null ? [] : mentionableUsers
    .filter((u) => {
      const q = mention.prefix.toLowerCase()
      if (!q) return true
      return u.username.toLowerCase().includes(q) || u.full_name.toLowerCase().includes(q)
    })
    .slice(0, 8)

  // Reset highlight when matches change
  useEffect(() => { setHighlightIdx(0) }, [mention?.prefix])

  const { data: notes = [], isLoading } = useQuery<CaseNote[]>({
    queryKey: ['case-notes', caseId],
    queryFn: async () => (await api.get<CaseNote[]>(`/cases/${caseId}/notes`)).data,
  })

  const postMut = useMutation({
    mutationFn: async (body: string) => {
      const res = await api.post<CaseNote>(`/cases/${caseId}/notes`, { body })
      return res.data
    },
    onSuccess: () => {
      setDraft('')
      queryClient.invalidateQueries({ queryKey: ['case-notes', caseId] })
      queryClient.invalidateQueries({ queryKey: ['case', caseId] })
    },
  })

  const submit = () => {
    if (!draft.trim() || postMut.isPending) return
    postMut.mutate(draft.trim())
  }

  const onDraftChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setDraft(e.target.value)
    const caret = e.target.selectionStart ?? e.target.value.length
    setMention(detectMention(e.target.value, caret))
  }

  const onSelectionChange = () => {
    const el = textareaRef.current
    if (!el) return
    setMention(detectMention(el.value, el.selectionStart ?? el.value.length))
  }

  const insertMention = (user: User) => {
    const el = textareaRef.current
    if (!el || !mention) return
    const before = draft.slice(0, mention.startIdx)
    const after = draft.slice((el.selectionStart ?? draft.length))
    const insertion = `@${user.username} `
    const newValue = before + insertion + after
    setDraft(newValue)
    setMention(null)
    // Reposition caret right after the inserted mention
    requestAnimationFrame(() => {
      const pos = before.length + insertion.length
      el.focus()
      el.setSelectionRange(pos, pos)
    })
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Mention dropdown navigation takes priority
    if (mention && matches.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setHighlightIdx((i) => (i + 1) % matches.length)
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setHighlightIdx((i) => (i - 1 + matches.length) % matches.length)
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        insertMention(matches[highlightIdx])
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setMention(null)
        return
      }
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
      <div className="flex items-center gap-2 mb-3">
        <MessageSquare className="w-4 h-4 text-gray-500" />
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Notes</h3>
        {notes.length > 0 && (
          <span className="text-xs text-gray-400">({notes.length})</span>
        )}
      </div>

      {isLoading ? (
        <p className="text-xs text-gray-400 italic">Loading notes…</p>
      ) : notes.length === 0 ? (
        <p className="text-xs text-gray-400 italic mb-3">No notes yet. Be the first to add one.</p>
      ) : (
        <ul className="space-y-3 mb-4">
          {notes.map((n) => (
            <li key={n.id} className="border-l-2 border-gray-200 pl-3 py-0.5">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-sm font-semibold text-gray-800">
                  {n.author?.full_name ?? 'Unknown'}
                </span>
                {n.author?.role && (
                  <span className={`text-[10px] font-medium px-1.5 py-px rounded ${ROLE_PILL[n.author.role]}`}>
                    {n.author.role}
                  </span>
                )}
                <span className="text-xs text-gray-400">
                  {formatDate(n.created_at)}
                </span>
              </div>
              <p className="text-sm text-gray-700 whitespace-pre-wrap">{renderWithMentions(n.body)}</p>
            </li>
          ))}
        </ul>
      )}

      {/* Compose */}
      <div className="border-t border-gray-100 pt-3 relative">
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={onDraftChange}
          onKeyDown={onKeyDown}
          onKeyUp={onSelectionChange}
          onClick={onSelectionChange}
          onBlur={() => setTimeout(() => setMention(null), 150)}
          rows={2}
          placeholder="Add a note… type @ to mention someone (Ctrl/Cmd+Enter to submit)"
          className="w-full text-sm border border-gray-200 rounded-lg p-2 focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100 resize-none"
        />

        {/* Mention autocomplete popup */}
        {mention && matches.length > 0 && (
          <div className="absolute left-2 right-2 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-20 max-h-64 overflow-y-auto">
            <div className="px-3 py-1.5 border-b border-gray-100 flex items-center gap-1.5">
              <AtSign className="w-3 h-3 text-gray-400" />
              <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">Mention</span>
              <span className="text-[11px] text-gray-400 ml-auto">↑↓ navigate · Enter to insert · Esc to dismiss</span>
            </div>
            {matches.map((u, i) => {
              const active = i === highlightIdx
              return (
                <button
                  key={u.id}
                  onMouseDown={(e) => { e.preventDefault(); insertMention(u) }}
                  onMouseEnter={() => setHighlightIdx(i)}
                  className={`w-full text-left px-3 py-1.5 flex items-center gap-2 transition-colors ${
                    active ? 'bg-indigo-50' : 'hover:bg-gray-50'
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm truncate ${active ? 'font-semibold text-indigo-700' : 'text-gray-800'}`}>
                      {u.full_name}
                    </p>
                    <p className="text-[11px] text-gray-400 font-mono">@{u.username}</p>
                  </div>
                  <span className={`text-[10px] font-medium px-1.5 py-px rounded ${ROLE_PILL[u.role]}`}>
                    {u.role}
                  </span>
                </button>
              )
            })}
          </div>
        )}

        <div className="flex items-center justify-between mt-2">
          <p className="text-[11px] text-gray-400">
            Type <span className="font-mono">@</span> to mention a teammate. Notes are visible to all users and recorded in the audit log.
          </p>
          <button
            onClick={submit}
            disabled={!draft.trim() || postMut.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-gray-200 disabled:text-gray-400 transition-colors"
          >
            <Send className="w-3 h-3" />
            {postMut.isPending ? 'Posting…' : 'Add note'}
          </button>
        </div>
        {postMut.isError && (
          <p className="text-xs text-red-600 mt-1">
            {(postMut.error as any)?.response?.data?.detail ?? 'Failed to post note'}
          </p>
        )}
      </div>
    </div>
  )
}
