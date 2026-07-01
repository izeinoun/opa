// Global slide-over chat panel for the read-only OPA Assistant.
// Streams from POST /api/assistant/chat/stream (SSE). Mirrors ClearLink's
// Charlie pattern: live assistant text + tool-call trace + ask_user soft
// buttons. Conversation history is kept client-side in Anthropic message
// format; the server is stateless.
import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import DOMPurify from 'dompurify'
import { sanitizeAssistantOutput } from '../../lib/sanitizeAssistantOutput'
import type { CaseGuidance, NextAction } from '../../types/guidance'
import type { ChatContext } from '../../types/assistant'

// A message is an "HTML card" when it leads with a block-level HTML element.
// Such content is rendered as sanitized HTML (browsers parse it leniently),
// NOT through Markdown — whose blank-line-terminates-HTML-block rule otherwise
// makes big multi-section cards leak raw <div> source partway through.
const HTML_CARD = /<(div|table|section|article|figure|main|header|h[1-6])[\s/>]/i
import { Bot, Send, X, Wrench, AlertTriangle, Loader2, ArrowRight, Check } from 'lucide-react'
import { API_BASE } from '../../services/api'

// ── Anthropic message types (minimal) ─────────────────────────────────────
type ContentBlock =
  | { type: 'text'; text: string }
  | { type: 'tool_use'; id: string; name: string; input: unknown }
  | { type: 'tool_result'; tool_use_id: string; content: string; is_error?: boolean }
type Message = { role: 'user' | 'assistant'; content: string | ContentBlock[] }

type StreamItem =
  | { kind: 'text'; text: string }
  | { kind: 'tool'; id: string; name: string; status: 'running' | 'done' | 'error'; error?: string }

type Awaiting = { question: string; options: string[]; tool_use_id: string }
// A proposed write awaiting the user's Confirm/Cancel (the write gate).
type Confirming = { summary: string; preview?: string; action: string; tool_use_id: string }

// What the user is currently looking at, so the assistant resolves "this case"
// from the first message. Seeded from the route; a case directive can override
// it later (Part 4). See docs/workflow-guidance-plan.md (Amendment 3).
function deriveRouteContext(pathname: string): ChatContext {
  const m = pathname.match(/^\/cases\/(\d+)/)
  if (m) return { active_case_id: parseInt(m[1], 10), active_view: 'case' }
  if (pathname.startsWith('/worklist')) return { active_view: 'worklist' }
  if (pathname.startsWith('/closed-cases')) return { active_view: 'closed_cases' }
  if (pathname === '/' || pathname.startsWith('/dashboard')) return { active_view: 'dashboard' }
  return {}
}

const SUGGESTIONS = [
  'How many high-priority open cases are there?',
  "How's the recovery pipeline doing?",
  'Show me my productivity this month',
]

const CASE_SUGGESTIONS = [
  'What are the key findings on this case?',
  'Walk me through the next workflow steps',
  'What is the at-risk amount for this case?',
]

interface AssistantPanelProps {
  open: boolean
  onClose: () => void
  isDrawerMode?: boolean
  context?: ChatContext
}

export default function AssistantPanel({ open, onClose, isDrawerMode = false, context: propContext }: AssistantPanelProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [stream, setStream] = useState<StreamItem[]>([])
  const [awaiting, setAwaiting] = useState<Awaiting | null>(null)
  const [confirming, setConfirming] = useState<Confirming | null>(null)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [sessionLoaded, setSessionLoaded] = useState(!isDrawerMode)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Active-case context. A case directive pins a case; otherwise we fall back
  // to whatever the route says is on screen (or the prop context in drawer mode).
  const location = useLocation()
  const navigate = useNavigate()
  const [pinnedCaseId, setPinnedCaseId] = useState<number | null>(null)
  const context = useMemo<ChatContext>(() => {
    if (pinnedCaseId) return { active_case_id: pinnedCaseId, active_view: 'case' }
    if (isDrawerMode && propContext) return propContext
    return deriveRouteContext(location.pathname)
  }, [pinnedCaseId, location.pathname, isDrawerMode, propContext])

  // Cockpit: the case lifecycle shown in the left column + the Next pill /
  // remaining-steps line in the chat. Fed by `guidance` on directive/final.
  const [cockpitCaseId, setCockpitCaseId] = useState<number | null>(null)
  const [cockpitCaption, setCockpitCaption] = useState<string>('')
  const [guidance, setGuidance] = useState<CaseGuidance | null>(null)

  // Navigate the main app (behind the panel) to a directive's view so the chat
  // drives the cockpit. Read-only / safe.
  function navigateToDirective(view: string | undefined, params: Record<string, unknown> = {}) {
    if (view === 'case' && params.case_id) {
      const tab = params.tab ? `?tab=${params.tab}` : ''
      navigate(`/cases/${params.case_id}${tab}`)
    } else if (view === 'worklist') {
      navigate('/worklist')
    } else if (view === 'my_dashboard') {
      navigate('/')
    }
  }

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, stream, awaiting, loading])

  // Load persisted session whenever the active case changes (drawer mode only)
  useEffect(() => {
    if (!isDrawerMode) return
    const caseId = context.active_case_id
    // Reset all chat state
    setMessages([]); setStream([]); setAwaiting(null); setConfirming(null)
    setError(''); setSuggestions([])
    setCockpitCaseId(null); setCockpitCaption(''); setGuidance(null); setPinnedCaseId(null)
    if (!caseId) { setSessionLoaded(true); return }
    setSessionLoaded(false)
    fetch(`${API_BASE}/cases/${caseId}/chat`, { credentials: 'include' })
      .then(r => r.ok ? r.json() : { messages: [] })
      .then(data => { if (data.messages?.length) setMessages(data.messages) })
      .catch(() => {})
      .finally(() => setSessionLoaded(true))
  }, [isDrawerMode, context.active_case_id]) // eslint-disable-line react-hooks/exhaustive-deps

  function reset() {
    setMessages([]); setStream([]); setAwaiting(null); setConfirming(null); setError(''); setSuggestions([])
    setCockpitCaseId(null); setCockpitCaption(''); setGuidance(null); setPinnedCaseId(null)
  }

  async function saveChatSession(msgs: Message[]) {
    const caseId = context.active_case_id
    if (!isDrawerMode || !caseId) return
    try {
      await fetch(`${API_BASE}/cases/${caseId}/chat`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: msgs }),
      })
    } catch { /* silent */ }
  }

  async function clearSession() {
    const caseId = context.active_case_id
    if (isDrawerMode && caseId) {
      try {
        await fetch(`${API_BASE}/cases/${caseId}/chat`, { method: 'DELETE', credentials: 'include' })
      } catch { /* silent */ }
    }
    reset()
  }

  // next_action kinds that change the case → route through the chat so the agent
  // proposes a confirm_action (write gate). Navigational kinds deep-link instead.
  const WRITE_KINDS = new Set([
    'take_ownership', 'start_review', 'submit_decision',
    'supervisor_decision', 'adjudicate_without_837', 'record_recovery',
  ])
  function handleNext(action: NextAction) {
    if (WRITE_KINDS.has(action.kind)) {
      // Clicking proposes the write via the agent, which asks for confirmation.
      send([...messages, { role: 'user', content: action.label }])
      return
    }
    const params = action.target?.params
    if (action.target?.view === 'case' && params?.case_id) {
      navigateToDirective('case', params)
    } else {
      send([...messages, { role: 'user', content: action.label }])
    }
  }

  async function send(next: Message[]) {
    setLoading(true); setError(''); setStream([]); setAwaiting(null); setConfirming(null); setSuggestions([])
    setMessages(next)
    try {
      const res = await fetch(`${API_BASE}/assistant/chat/stream`, {
        method: 'POST',
        credentials: 'include', // Send httpOnly cookies
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ messages: next, context }),
      })
      if (!res.ok || !res.body) throw new Error((await res.text().catch(() => '')) || `HTTP ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        let idx
        while ((idx = buf.indexOf('\n\n')) !== -1) {
          const frame = buf.slice(0, idx); buf = buf.slice(idx + 2)
          for (const line of frame.split('\n')) {
            if (!line.startsWith('data: ')) continue
            try { handleEvent(JSON.parse(line.slice(6))) } catch { /* ignore */ }
          }
        }
      }
    } catch (e: any) {
      setError(e?.message || 'Assistant error. Try again.')
      setStream([])
    } finally {
      setLoading(false)
    }
  }

  function handleEvent(evt: any) {
    switch (evt.type) {
      case 'assistant_text':
        setStream((s) => [...s, { kind: 'text', text: evt.text }])
        break
      case 'tool_start':
        setStream((s) => [...s, { kind: 'tool', id: evt.id, name: evt.name, status: 'running' }])
        break
      case 'tool_end':
        setStream((s) => s.map((i) =>
          i.kind === 'tool' && i.id === evt.id
            ? { ...i, status: evt.ok ? 'done' : 'error', error: evt.error }
            : i))
        break
      case 'directive': {
        // Chat asked to mount a view. Drive the main app (behind the panel) and,
        // for a case, pin it + load its lifecycle into the cockpit.
        navigateToDirective(evt.view, evt.params || {})
        if (evt.view === 'case' && evt.params?.case_id) {
          setCockpitCaseId(evt.params.case_id)
          setPinnedCaseId(evt.params.case_id)
          setCockpitCaption(evt.caption || `Case ${evt.params.case_id}`)
        }
        if (evt.guidance) setGuidance(evt.guidance as CaseGuidance)
        break
      }
      case 'final':
        setMessages(evt.messages); setStream([]); setAwaiting(null)
        setSuggestions(Array.isArray(evt.suggestions) ? evt.suggestions : [])
        if (evt.guidance) setGuidance(evt.guidance as CaseGuidance)
        saveChatSession(evt.messages)
        break
      case 'awaiting_user':
        setMessages(evt.messages); setStream([])
        setAwaiting({ question: evt.question, options: evt.options || [], tool_use_id: evt.tool_use_id })
        break
      case 'awaiting_confirmation':
        setMessages(evt.messages); setStream([])
        setConfirming({
          summary: evt.summary || 'Apply this change?',
          preview: evt.preview,
          action: evt.action,
          tool_use_id: evt.tool_use_id,
        })
        break
      case 'error':
        setError(evt.error || 'Assistant error.'); setStream([])
        break
    }
  }

  function submit() {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    send([...messages, { role: 'user', content: text }])
  }

  function pickOption(option: string) {
    if (!awaiting || loading) return
    const next: Message[] = [
      ...messages,
      { role: 'user', content: [{ type: 'tool_result', tool_use_id: awaiting.tool_use_id, content: option }] },
    ]
    setAwaiting(null)
    send(next)
  }

  // Confirm / cancel a proposed write. The server executes the write only on
  // CONFIRMED (see the agent's _handle_confirmation).
  function respondConfirm(ok: boolean) {
    if (!confirming || loading) return
    const next: Message[] = [
      ...messages,
      { role: 'user', content: [{ type: 'tool_result', tool_use_id: confirming.tool_use_id, content: ok ? 'CONFIRMED' : 'CANCELLED' }] },
    ]
    setConfirming(null)
    send(next)
  }

  if (!open) return null

  const empty = messages.length === 0 && stream.length === 0 && !loading && !error

  // A tool_result block in a user-role message is one of two things:
  //  • the user's answer to an ask_user prompt (a short soft-button pick) → show it
  //  • a real tool's execution output (search_cases, etc.) fed back as context
  //    → internal, must NOT be rendered (this is what dumped raw JSON into the
  //    chat). Collect the tool_use ids that came from ask_user so MessageView
  //    can tell them apart.
  const askUserIds = new Set<string>()
  for (const m of messages) {
    if (m.role === 'assistant' && Array.isArray(m.content)) {
      for (const b of m.content) {
        if (b.type === 'tool_use' && b.name === 'ask_user') askUserIds.add(b.id)
      }
    }
  }

  // In drawer mode, render just the content (no fixed overlays)
  // In modal mode, render the full modal with overlay
  if (isDrawerMode) {
    return (
      <aside className="w-full h-full bg-white flex flex-col">
        {/* Drawer toolbar */}
        {(messages.length > 0 || !sessionLoaded) && (
          <div className="flex items-center justify-end px-3 py-1.5 border-b border-gray-100 flex-shrink-0">
            {messages.length > 0 && !loading && (
              <button
                onClick={clearSession}
                className="text-[11px] text-gray-400 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100 transition-colors"
              >
                Clear chat
              </button>
            )}
          </div>
        )}
        {/* Body: chat column (full width) */}
        <div className="flex flex-1 min-h-0">
        <div className="flex flex-col flex-1 min-h-0">
        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3 bg-gray-50">
          {!sessionLoaded ? (
            <div className="flex items-center justify-center mt-12 gap-2 text-xs text-gray-400">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading conversation…
            </div>
          ) : empty && (
            <div className="text-center mt-8">
              <Bot className="w-8 h-8 text-gray-300 mx-auto mb-2" />
              <p className="text-sm text-gray-500">Ask about cases, claims, providers, or metrics.</p>
              <div className="mt-4 space-y-2">
                {(context.active_case_id ? CASE_SUGGESTIONS : SUGGESTIONS).map((s) => (
                  <button key={s} onClick={() => send([...messages, { role: 'user', content: s }])}
                    className="block w-full text-left text-xs px-3 py-2 rounded-lg border border-gray-200 bg-white hover:border-[#FE017D]/40 hover:bg-[#FE017D]/5 text-gray-600">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => <MessageView key={i} message={m} askUserIds={askUserIds} />)}

          {/* Live stream (current turn) */}
          {stream.map((item, i) =>
            item.kind === 'text'
              ? <AssistantBubble key={i} text={item.text} />
              : <ToolLine key={i} name={item.name} status={item.status} error={item.error} />
          )}

          {loading && stream.length === 0 && (
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Thinking…
            </div>
          )}

          {awaiting && (
            <div className="rounded-xl border border-sky-200 bg-sky-50 p-3">
              <p className="text-sm text-gray-800 mb-2">{awaiting.question}</p>
              <div className="flex flex-wrap gap-2">
                {awaiting.options.map((o) => (
                  <button key={o} onClick={() => pickOption(o)}
                    className="text-xs px-3 py-1.5 rounded-full border border-sky-300 bg-white hover:bg-sky-100 text-sky-800">
                    {o}
                  </button>
                ))}
              </div>
            </div>
          )}

          {confirming && (
            <div className="rounded-xl border border-amber-300 bg-amber-50 p-3">
              <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-amber-700">
                <AlertTriangle className="w-3.5 h-3.5" /> Confirm change
              </p>
              <p className="text-sm text-gray-900 mt-1.5 font-medium">{confirming.summary}</p>
              {confirming.preview && (
                <p className="text-xs text-amber-800 mt-1">{confirming.preview}</p>
              )}
              <div className="flex gap-2 mt-3">
                <button onClick={() => respondConfirm(true)} disabled={loading}
                  className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-[#FE017D] text-white hover:bg-pink-600 disabled:opacity-50">
                  Confirm
                </button>
                <button onClick={() => respondConfirm(false)} disabled={loading}
                  className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-gray-300 bg-white text-gray-700 hover:bg-gray-50 disabled:opacity-50">
                  Cancel
                </button>
              </div>
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg p-2.5">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" /> <span>{error}</span>
            </div>
          )}

          {/* Suggested follow-ups (from the model, stripped server-side) */}
          {!loading && !awaiting && suggestions.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {suggestions.map((s) => (
                <button key={s} onClick={() => send([...messages, { role: 'user', content: s }])}
                  className="text-xs px-3 py-1.5 rounded-full border border-[#FE017D]/30 bg-[#FE017D]/5 text-[#be185d] hover:bg-[#FE017D]/10 transition-colors">
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Next step + remaining-steps line (grounded in real case state) */}
          {!loading && !awaiting && guidance && (
            <div className="pt-1 space-y-1.5">
              {guidance.next_action && guidance.next_action.actionable !== false && (
                <button
                  onClick={() => handleNext(guidance.next_action!)}
                  title={guidance.next_action.explanation}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-[#FE017D] hover:bg-pink-600 rounded-full transition-colors"
                >
                  Next <ArrowRight className="w-3 h-3" /> {guidance.next_action.label}
                </button>
              )}
              {guidance.remaining_summary && (
                <p className="text-[11px] text-gray-400">{guidance.remaining_summary}</p>
              )}
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-gray-200 p-3 flex-shrink-0">
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }}
              placeholder="Ask the assistant…"
              rows={1}
              disabled={loading}
              className="flex-1 resize-none text-sm border border-gray-200 rounded-lg px-3 py-2 max-h-32 focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]/40 disabled:bg-gray-50"
            />
            <button onClick={submit} disabled={loading || !input.trim()}
              className="p-2 rounded-lg bg-[#FE017D] text-white disabled:opacity-40 hover:bg-[#d4016a] transition-colors">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </button>
          </div>
        </div>
        </div>{/* /chat column */}
        </div>{/* /body row */}
      </aside>
    )
  }

  // Modal mode (original behavior)
  if (!open) return null
  return (
    <>
      <div className="fixed inset-0 bg-black/20 z-40" onClick={onClose} aria-hidden />
      <aside className="fixed top-0 right-0 bottom-0 w-[840px] max-w-[95vw] bg-white border-l border-gray-200 shadow-2xl z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 h-12 border-b border-gray-200 flex-shrink-0">
          <div className="w-7 h-7 rounded-lg bg-[#FE017D]/10 flex items-center justify-center">
            <Bot className="w-4 h-4 text-[#FE017D]" />
          </div>
          <div className="flex items-center gap-1">
            {messages.length > 0 && (
              <button onClick={reset} className="text-[11px] text-gray-400 hover:text-gray-700 px-2 py-1 rounded hover:bg-gray-100">
                Clear
              </button>
            )}
            <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-700">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Body: chat */}
        <div className="flex flex-1 min-h-0">
          <div className="flex flex-col flex-1 min-h-0 p-3 overflow-y-auto">
            {!messages.length && !stream.length && !loading && !error && (
              <div className="flex flex-col items-center justify-center h-full text-center text-gray-500 gap-3">
                <Bot className="w-8 h-8 text-gray-300" />
                <div>
                  <p className="text-sm font-semibold mb-2">How can I help?</p>
                  <div className="space-y-1.5">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        onClick={() => send([...messages, { role: 'user', content: s }])}
                        className="block text-xs hover:text-[#FE017D] transition-colors"
                      >
                        • {s}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {error && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 text-red-800 text-sm mb-3">
                <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <p>{error}</p>
              </div>
            )}

            {messages.concat(stream.length > 0 ? [{ role: 'assistant', content: '' } as Message] : []).map((msg, i) => (
              <div key={i} className="mb-2.5">
                <MessageView message={msg} askUserIds={askUserIds} />
              </div>
            ))}

            {stream.map((item, i) => (
              <div key={i}>
                {item.kind === 'text' && <AssistantBubble text={item.text} />}
                {item.kind === 'tool' && <ToolLine name={item.name} status={item.status} error={item.error} />}
              </div>
            ))}

            {loading && stream.length === 0 && (
              <div className="flex items-center gap-2 text-xs text-gray-400">
                <Loader2 className="w-3 h-3 animate-spin" />
                Thinking…
              </div>
            )}

            <div ref={scrollRef} />
          </div>
        </div>

        {/* Write gate (confirm action before execution) */}
        {confirming && (
          <div className="border-t border-gray-200 p-3 bg-gray-50">
            <p className="text-xs font-semibold text-gray-700 mb-2">{confirming.summary}</p>
            {confirming.preview && (
              <div className="text-[11px] text-gray-600 mb-3 p-2 bg-white rounded border border-gray-100 max-h-24 overflow-y-auto">
                {confirming.preview}
              </div>
            )}
            <div className="flex gap-2">
              <button onClick={() => respondConfirm(true)} className="flex-1 px-2 py-1.5 bg-[#FE017D] text-white text-xs font-semibold rounded-lg hover:bg-[#E60070] transition-colors flex items-center justify-center gap-1">
                <Check className="w-3 h-3" />
                Confirm
              </button>
              <button onClick={() => setConfirming(null)} className="flex-1 px-2 py-1.5 bg-gray-200 text-gray-900 text-xs font-semibold rounded-lg hover:bg-gray-300 transition-colors">
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Ask user (soft buttons for soft choices) */}
        {awaiting && (
          <div className="border-t border-gray-200 p-3 bg-gray-50">
            <p className="text-xs font-semibold text-gray-700 mb-2">{awaiting.question}</p>
            <div className="grid grid-cols-2 gap-2">
              {awaiting.options.map((opt) => (
                <button key={opt} onClick={() => pickOption(opt)} className="px-2 py-1.5 bg-white border border-gray-200 text-xs font-semibold rounded-lg hover:bg-gray-50 transition-colors">
                  {opt}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Input */}
        <div className="border-t border-gray-200 flex gap-2 p-3 flex-shrink-0 bg-gray-50">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') send([...messages, { role: 'user', content: input }])
            }}
            placeholder="Ask the assistant…"
            disabled={loading}
            rows={1}
            className="flex-1 text-sm p-2 border border-gray-300 rounded-lg focus:border-[#FE017D] focus:outline-none resize-none disabled:opacity-50"
          />
          <button onClick={() => send([...messages, { role: 'user', content: input }])} disabled={loading || !input.trim()} title="Send (Cmd/Ctrl + Enter)" className="text-[#FE017D] hover:text-[#E60070] disabled:text-gray-300 transition-colors p-2">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </button>
        </div>
      </aside>
    </>
  )
}

// ── Rendering helpers ──────────────────────────────────────────────────────
function MessageView({ message, askUserIds }: { message: Message; askUserIds: Set<string> }) {
  if (message.role === 'user') {
    // Plain user text.
    if (typeof message.content === 'string') return <UserBubble text={message.content} />
    // A tool_result: only render it as the user's pick when it answers an
    // ask_user prompt. Real tool-execution output (search_cases, etc.) is
    // internal context for the model — never paint it in the chat.
    const tr = message.content.find((b) => b.type === 'tool_result') as
      | Extract<ContentBlock, { type: 'tool_result' }> | undefined
    if (tr && askUserIds.has(tr.tool_use_id)) return <UserBubble text={tr.content} />
    return null
  }
  // assistant: render text blocks; show a chip for each tool_use
  const blocks = Array.isArray(message.content) ? message.content : [{ type: 'text', text: message.content } as ContentBlock]
  return (
    <>
      {blocks.map((b, i) => {
        if (b.type === 'text' && b.text) return <AssistantBubble key={i} text={b.text} />
        if (b.type === 'tool_use') return <ToolLine key={i} name={b.name} status="done" />
        return null
      })}
    </>
  )
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] bg-[#FE017D] text-white text-sm rounded-2xl rounded-br-sm px-3 py-2 whitespace-pre-wrap">
        {text}
      </div>
    </div>
  )
}

function AssistantBubble({ text }: { text: string }) {
  // Remove markup that shouldn't be visible to users
  const cleanedText = sanitizeAssistantOutput(text)

  return (
    <div className="max-w-[92%] bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-3 py-2 text-sm text-gray-800 prose prose-sm max-w-none prose-p:my-1 prose-headings:my-1.5 prose-ul:my-1 prose-li:my-0">
      {HTML_CARD.test(cleanedText)
        ? <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(cleanedText) }} />
        : (
          /* remark-gfm → GFM tables/strikethrough; rehype-raw → inline HTML like <br> */
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{cleanedText}</ReactMarkdown>
        )}
    </div>
  )
}

const TOOL_LABELS: Record<string, { running: string; done: string }> = {
  search_members:              { running: 'Searching for member…',                   done: 'Member identified' },
  search_cases:                { running: 'Checking PayGuard recovery cases…',       done: 'PayGuard cases loaded' },
  get_case:                    { running: 'Loading case details…',                   done: 'Case loaded' },
  get_case_guidance:           { running: 'Calculating next steps…',                 done: 'Guidance ready' },
  get_case_notes:              { running: 'Reading case notes…',                     done: 'Notes loaded' },
  get_payguard_dashboard:      { running: 'Loading PayGuard dashboard…',             done: 'Dashboard ready' },
  get_daily_briefing:          { running: 'Pulling your daily briefing…',            done: 'Briefing ready' },
  list_prepay_claims:          { running: 'Checking ClaimGuard pre-pay claims…',     done: 'ClaimGuard claims loaded' },
  get_prepay_claim:            { running: 'Loading pre-pay claim…',                  done: 'Claim loaded' },
  get_prepay_dashboard:        { running: 'Loading ClaimGuard dashboard…',           done: 'Dashboard ready' },
  get_siu_dashboard:           { running: 'Loading SIU investigation metrics…',      done: 'SIU dashboard ready' },
  list_provider_risk:          { running: 'Analyzing provider risk…',                done: 'Risk analysis ready' },
  get_member_360:              { running: 'Building cross-system member profile…',   done: 'Member 360 complete' },
  list_medications:            { running: 'Querying ClearLink — medications…',       done: 'Medications retrieved' },
  list_diagnoses:              { running: 'Querying ClearLink — diagnoses…',         done: 'Diagnoses retrieved' },
  list_dates_of_service:       { running: 'Fetching encounter history…',             done: 'Encounters retrieved' },
  get_claims_window:           { running: 'Fetching ClearLink claim history…',       done: 'Claim window loaded' },
  get_labs_window:             { running: 'Fetching lab results…',                   done: 'Labs retrieved' },
  list_prior_authorizations:   { running: 'Checking prior authorizations…',          done: 'Prior auths loaded' },
  get_member_demographics:     { running: 'Querying ClearLink eligibility…',         done: 'Eligibility verified' },
  get_my_dashboard:            { running: 'Loading your performance dashboard…',     done: 'Dashboard ready' },
  send_notice_to_provider:     { running: 'Sending notice to provider…',             done: 'Notice delivered' },
  send_provider_inquiry:       { running: 'Sending inquiry to provider…',            done: 'Inquiry sent' },
  search_claimguard_claims:    { running: 'Searching ClaimGuard claims…',            done: 'Claims found' },
}

function ToolLine({ name, status, error }: { name: string; status: 'running' | 'done' | 'error'; error?: string }) {
  const label = TOOL_LABELS[name]
  const text =
    status === 'running' ? (label?.running ?? `Calling ${name}…`) :
    status === 'error'   ? `Failed: ${label?.running?.replace('…', '') ?? name}` :
                           (label?.done ?? name)
  return (
    <div className="flex items-center gap-1.5 text-[11px] pl-1 py-0.5" title={error || name}>
      {status === 'running'
        ? <Loader2 className="w-3 h-3 animate-spin text-[#FE017D] flex-shrink-0" />
        : <Wrench className={`w-3 h-3 flex-shrink-0 ${status === 'error' ? 'text-red-400' : 'text-gray-300'}`} />}
      <span className={
        status === 'running' ? 'text-gray-600 font-medium' :
        status === 'error'   ? 'text-red-400' :
                               'text-gray-400'
      }>
        {text}
      </span>
    </div>
  )
}
