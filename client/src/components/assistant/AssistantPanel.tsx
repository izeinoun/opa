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
import CaseLifecycleRail from '../workflow/CaseLifecycleRail'
import type { CaseGuidance, NextAction } from '../../types/guidance'

// A message is an "HTML card" when it leads with a block-level HTML element.
// Such content is rendered as sanitized HTML (browsers parse it leniently),
// NOT through Markdown — whose blank-line-terminates-HTML-block rule otherwise
// makes big multi-section cards leak raw <div> source partway through.
const HTML_CARD = /<(div|table|section|article|figure|main|header|h[1-6])[\s/>]/i
import { Bot, Send, X, Wrench, AlertTriangle, Loader2, ArrowRight, Workflow } from 'lucide-react'
import { API_BASE, JWT_TOKEN_KEY } from '../../services/api'

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
type ChatContext = { active_case_id?: number; active_view?: string }
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

export default function AssistantPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [stream, setStream] = useState<StreamItem[]>([])
  const [awaiting, setAwaiting] = useState<Awaiting | null>(null)
  const [confirming, setConfirming] = useState<Confirming | null>(null)
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  // Active-case context. A case directive pins a case; otherwise we fall back
  // to whatever the route says is on screen.
  const location = useLocation()
  const navigate = useNavigate()
  const [pinnedCaseId, setPinnedCaseId] = useState<number | null>(null)
  const context = useMemo<ChatContext>(() => {
    if (pinnedCaseId) return { active_case_id: pinnedCaseId, active_view: 'case' }
    return deriveRouteContext(location.pathname)
  }, [pinnedCaseId, location.pathname])

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

  function reset() {
    setMessages([]); setStream([]); setAwaiting(null); setConfirming(null); setError(''); setSuggestions([])
    setCockpitCaseId(null); setCockpitCaption(''); setGuidance(null); setPinnedCaseId(null)
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
        headers: {
          'Content-Type': 'application/json',
          // JWT token from localStorage — required for authenticated API access.
          // SSE uses fetch directly, bypassing axios interceptor, so we attach it manually.
          ...(localStorage.getItem(JWT_TOKEN_KEY)
            ? { Authorization: `Bearer ${localStorage.getItem(JWT_TOKEN_KEY)}` }
            : {}),
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
        // Grounded workflow guidance for the cockpit rail + Next pill.
        if (evt.guidance) setGuidance(evt.guidance as CaseGuidance)
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

  return (
    <>
      <div className="fixed inset-0 bg-black/20 z-40" onClick={onClose} aria-hidden />
      <aside className="fixed top-0 right-0 bottom-0 w-[840px] max-w-[95vw] bg-white border-l border-gray-200 shadow-2xl z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 h-12 border-b border-gray-200 flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-[#FE017D]/10 flex items-center justify-center">
              <Bot className="w-4 h-4 text-[#FE017D]" />
            </div>
            <div className="leading-tight">
              <p className="text-sm font-semibold text-gray-900">OPA Assistant</p>
              <p className="text-[10px] text-gray-400">Answers + actions · confirms before changes</p>
            </div>
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

        {/* Body: optional workflow cockpit column + chat column */}
        <div className="flex flex-1 min-h-0">
        {cockpitCaseId && guidance && (
          <aside className="w-[260px] flex-shrink-0 border-r border-gray-200 bg-white overflow-y-auto p-3.5">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-gray-500">
              <Workflow className="w-3.5 h-3.5" /> Workflow
            </p>
            {cockpitCaption && (
              <button
                onClick={() => navigateToDirective('case', { case_id: cockpitCaseId })}
                className="mt-1 text-sm font-bold text-gray-900 hover:text-[#FE017D] font-mono"
              >
                {cockpitCaption}
              </button>
            )}
            <div className="mt-3">
              <CaseLifecycleRail steps={guidance.lifecycle} orientation="vertical" />
            </div>
          </aside>
        )}
        <div className="flex flex-col flex-1 min-h-0">
        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3 bg-gray-50">
          {empty && (
            <div className="text-center mt-8">
              <Bot className="w-8 h-8 text-gray-300 mx-auto mb-2" />
              <p className="text-sm text-gray-500">Ask about cases, claims, providers, or metrics.</p>
              <div className="mt-4 space-y-2">
                {SUGGESTIONS.map((s) => (
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
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
        </div>{/* /chat column */}
        </div>{/* /body row */}
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
  return (
    <div className="max-w-[92%] bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-3 py-2 text-sm text-gray-800 prose prose-sm max-w-none prose-p:my-1 prose-headings:my-1.5 prose-ul:my-1 prose-li:my-0">
      {HTML_CARD.test(text)
        ? <div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(text) }} />
        : (
          /* remark-gfm → GFM tables/strikethrough; rehype-raw → inline HTML like <br> */
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{text}</ReactMarkdown>
        )}
    </div>
  )
}

function ToolLine({ name, status, error }: { name: string; status: 'running' | 'done' | 'error'; error?: string }) {
  return (
    <div className="flex items-center gap-2 text-[11px] text-gray-400 pl-1" title={error || ''}>
      {status === 'running'
        ? <Loader2 className="w-3 h-3 animate-spin" />
        : <Wrench className={`w-3 h-3 ${status === 'error' ? 'text-red-400' : ''}`} />}
      <span className={status === 'error' ? 'text-red-400' : ''}>
        {status === 'running' ? 'Calling' : status === 'error' ? 'Failed' : 'Used'} <span className="font-mono">{name}</span>
      </span>
    </div>
  )
}
