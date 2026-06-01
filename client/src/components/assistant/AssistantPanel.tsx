// Global slide-over chat panel for the read-only OPA Assistant.
// Streams from POST /api/assistant/chat/stream (SSE). Mirrors ClearLink's
// Charlie pattern: live assistant text + tool-call trace + ask_user soft
// buttons. Conversation history is kept client-side in Anthropic message
// format; the server is stateless.
import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Bot, Send, X, Wrench, AlertTriangle, Loader2 } from 'lucide-react'
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

const SUGGESTIONS = [
  'How many high-priority open cases are there?',
  "How's the recovery pipeline doing?",
  'Show me my productivity this month',
]

export default function AssistantPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [stream, setStream] = useState<StreamItem[]>([])
  const [awaiting, setAwaiting] = useState<Awaiting | null>(null)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, stream, awaiting, loading])

  function reset() {
    setMessages([]); setStream([]); setAwaiting(null); setError('')
  }

  async function send(next: Message[]) {
    setLoading(true); setError(''); setStream([]); setAwaiting(null)
    setMessages(next)
    try {
      const res = await fetch(`${API_BASE}/assistant/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          // Same identity + gate headers the axios interceptor sets — needed
          // because SSE uses fetch directly, bypassing that interceptor.
          'X-User-Id': localStorage.getItem('opa_user_id') ?? '',
          'X-User-Role': localStorage.getItem('opa_role') ?? 'analyst',
          ...(localStorage.getItem('opa_demo_token')
            ? { Authorization: `Bearer ${localStorage.getItem('opa_demo_token')}` }
            : {}),
        },
        body: JSON.stringify({ messages: next }),
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
      case 'final':
        setMessages(evt.messages); setStream([]); setAwaiting(null)
        break
      case 'awaiting_user':
        setMessages(evt.messages); setStream([])
        setAwaiting({ question: evt.question, options: evt.options || [], tool_use_id: evt.tool_use_id })
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

  if (!open) return null

  const empty = messages.length === 0 && stream.length === 0 && !loading && !error

  return (
    <>
      <div className="fixed inset-0 bg-black/20 z-40" onClick={onClose} aria-hidden />
      <aside className="fixed top-0 right-0 bottom-0 w-[420px] max-w-[90vw] bg-white border-l border-gray-200 shadow-2xl z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 h-12 border-b border-gray-200 flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-[#FE017D]/10 flex items-center justify-center">
              <Bot className="w-4 h-4 text-[#FE017D]" />
            </div>
            <div className="leading-tight">
              <p className="text-sm font-semibold text-gray-900">OPA Assistant</p>
              <p className="text-[10px] text-gray-400">Read-only · answers from your data</p>
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

          {messages.map((m, i) => <MessageView key={i} message={m} />)}

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

          {error && (
            <div className="flex items-start gap-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg p-2.5">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" /> <span>{error}</span>
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
      </aside>
    </>
  )
}

// ── Rendering helpers ──────────────────────────────────────────────────────
function MessageView({ message }: { message: Message }) {
  if (message.role === 'user') {
    // User text (string) or a tool_result (soft-button pick) → show the pick.
    if (typeof message.content === 'string') return <UserBubble text={message.content} />
    const tr = message.content.find((b) => b.type === 'tool_result') as
      | Extract<ContentBlock, { type: 'tool_result' }> | undefined
    if (tr) return <UserBubble text={tr.content} />
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
      <ReactMarkdown>{text}</ReactMarkdown>
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
