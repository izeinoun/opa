// Claims Control Room — the boss-facing "watch the robots work" demo. Ten claims
// ride ten conveyor lanes through nine stations in parallel; five clear
// end-to-end on their own (gold + confetti), five stop at the ⚖️ Decide fork
// for a human (amber). Every event is REAL post-pay pipeline output streamed
// from GET /api/demo/run (SSE) — only the portal upload + secure email are
// simulated. The visual formatting mirrors the static "Live Run" mock exactly:
// masthead + heartbeat pill, a 4-stat HUD, a PROGRESS bar, a colour legend, and
// a labelled "receipt" chip that rides each lane. Design: deep-indigo control
// room, plain ✓/!/active dots on the track with the emoji in the header row,
// tabular-nums HUD so digits don't jitter as they tick.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { API_BASE } from '../services/api'

// Cache the last COMPLETED run in sessionStorage so navigating away and back
// re-shows the results without a re-run (and without re-hitting the pipeline).
// Only 'done' runs are cached — a mid-run SSE stream can't be resumed, so there's
// nothing useful to restore from a partial run.
const CACHE_KEY = 'ccr:lastrun:v4'

// ── palette (light theme — matches the app: gray-100 page, white cards,
// gray-200 borders, brand pink for primary actions, Tailwind semantic states) ──
const C = {
  ground: '#ffffff',   // board (top of subtle gradient)
  ground2: '#f8fafc',  // board bottom / idle-dot fill (near-white)
  panel: '#ffffff',    // cards, board surfaces
  panel2: '#f9fafb',
  line: '#e5e7eb',     // borders (gray-200)
  ink: '#111827',      // primary text (gray-900)
  dim: '#6b7280',      // muted text (gray-500)
  faint: '#9ca3af',    // fainter text (gray-400)
  idle: '#e5e7eb',
  brand: '#FE017D',    // app primary accent (pink) — buttons + case links
  work: '#2563eb',     // blue-600   — a station is running
  done: '#16a34a',     // green-600  — a station finished / auto-recoup
  gold: '#d97706',     // amber-600  — auto-recouped, no human
  human: '#ea580c',    // orange-600 — needs a human
  red: '#dc2626',      // red-600
}
const CONFETTI_COLORS = ['#f59e0b', '#22c55e', '#3b82f6', '#FE017D', '#ea580c']

type StageMeta = { key: string; label: string; emoji: string }
type StageStatus = 'active' | 'done' | 'review' | 'error'

type Lane = {
  fileId: string
  label: string
  status: Record<string, StageStatus>
  reached: number            // furthest station index reached (drives the fill + chip)
  detail: string
  outcome?: string           // AUTO_RECOUP | REVIEW | CLEAN | ERROR
  amount?: number
  evidence?: number
  reason?: string
  caseNumber?: string | null
  caseSequence?: number | null   // drives the /cases/:seq deep-link
  deliveryEmail?: string | null  // provider contact the notice was sent to
  deliveryContact?: string | null
  deliveryRef?: string | null    // send confirmation reference (token or demo ref)
  deliverySent?: boolean         // true = real EmailJS send, false = simulated
}

type Particle = {
  x: number; y: number; vx: number; vy: number; g: number
  life: number; w: number; h: number; rot: number; vr: number; c: string
}

const SPEEDS = {
  '1×': { pace: 0.55, stagger: 0.35 },
  '2×': { pace: 0.28, stagger: 0.18 },
} as const
type Speed = keyof typeof SPEEDS

const money = (n: number) => '$' + Math.round(n).toLocaleString('en-US')

// Read the cached last-completed run (once, at mount) so the page can restore it.
function readCache(): { stages: StageMeta[]; lanes: Record<string, Lane>; order: string[]; totals: { auto: number; review: number; recovered: number } | null } | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

export default function ClaimsControlRoomPage() {
  const cached = useMemo(readCache, [])
  const [stages, setStages] = useState<StageMeta[]>(cached?.stages ?? [])
  const [lanes, setLanes] = useState<Record<string, Lane>>(cached?.lanes ?? {})
  const [order, setOrder] = useState<string[]>(cached?.order ?? [])
  const [phase, setPhase] = useState<'idle' | 'running' | 'done'>(cached ? 'done' : 'idle')
  const [speed, setSpeed] = useState<Speed>('1×')
  const [totals, setTotals] = useState<{ auto: number; review: number; recovered: number } | null>(cached?.totals ?? null)
  const [resetting, setResetting] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const stageIdx = useRef<Record<string, number>>({}) // stage key → column index (set at init)
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({})

  // confetti (canvas — bursts from the right edge of a lane that auto-recoups)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const partsRef = useRef<Particle[]>([])
  const rafRef = useRef<number | null>(null)
  const prefersReduced = useMemo(
    () => (typeof window !== 'undefined' ? window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false : false),
    [],
  )

  const decisionIdx = useMemo(() => stages.findIndex((s) => s.key === 'decision'), [stages])

  // Persist a completed run so a later visit to this route re-shows it verbatim.
  useEffect(() => {
    if (phase !== 'done') return
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify({ stages, lanes, order, totals }))
    } catch { /* storage full / disabled — non-fatal */ }
  }, [phase, stages, lanes, order, totals])

  // Live HUD tallies straight off the lanes so they tick as results land.
  const hud = useMemo(() => {
    let auto = 0, review = 0, recovered = 0, run = 0
    for (const id of order) {
      const l = lanes[id]
      if (!l) continue
      if (l.outcome === 'AUTO_RECOUP') { auto++; recovered += l.amount || 0 }
      else if (l.outcome === 'REVIEW') review++
      else if (Object.keys(l.status).length > 0) run++
    }
    return { auto, review, recovered, run }
  }, [lanes, order])

  // Overall progress: each lane's target is the full pipeline, or the fork for a
  // review lane; sum the stations cleared over the total. Denominator shrinks as
  // review lanes resolve, exactly like the static mock.
  const progress = useMemo(() => {
    const n = stages.length
    if (order.length === 0 || n === 0) return 0
    let sd = 0, stTot = 0
    for (const id of order) {
      const l = lanes[id]
      if (!l) { stTot += n; continue }
      const target = l.outcome === 'REVIEW' ? (decisionIdx >= 0 ? decisionIdx + 1 : n) : n
      stTot += target
      const started = Object.keys(l.status).length > 0 || !!l.outcome
      sd += started ? Math.min(l.reached + 1, target) : 0
    }
    return stTot ? Math.round((sd / stTot) * 100) : 0
  }, [lanes, order, stages, decisionIdx])

  // ── confetti machinery ───────────────────────────────────────────────────
  const tick = useCallback(() => {
    const cv = canvasRef.current
    if (!cv) return
    const cx = cv.getContext('2d')
    if (!cx) return
    cx.clearRect(0, 0, cv.width, cv.height)
    partsRef.current = partsRef.current.filter((p) => p.life > 0)
    for (const p of partsRef.current) {
      p.vy += p.g; p.x += p.vx; p.y += p.vy; p.rot += p.vr; p.life--
      cx.save(); cx.translate(p.x, p.y); cx.rotate(p.rot)
      cx.globalAlpha = Math.min(1, p.life / 25)
      cx.fillStyle = p.c; cx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h); cx.restore()
    }
    if (partsRef.current.length) rafRef.current = requestAnimationFrame(tick)
    else { rafRef.current = null; cx.clearRect(0, 0, cv.width, cv.height) }
  }, [])

  const fireConfetti = useCallback((fileId: string) => {
    if (prefersReduced) return
    const row = rowRefs.current[fileId]
    const cv = canvasRef.current
    if (!row || !cv) return
    const r = row.getBoundingClientRect()
    const x = r.right - 70, y = r.top + r.height / 2
    for (let i = 0; i < 34; i++) {
      const a = Math.random() * Math.PI * 2, sp = 3 + Math.random() * 6
      partsRef.current.push({
        x, y, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp - 3, g: 0.16 + Math.random() * 0.1,
        life: 60 + Math.random() * 30, w: 5 + Math.random() * 5, h: 7 + Math.random() * 6,
        rot: Math.random() * 6, vr: (Math.random() - 0.5) * 0.4, c: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
      })
    }
    if (!rafRef.current) rafRef.current = requestAnimationFrame(tick)
  }, [prefersReduced, tick])

  useEffect(() => {
    const cv = canvasRef.current
    if (!cv) return
    const size = () => { cv.width = window.innerWidth; cv.height = window.innerHeight }
    size()
    window.addEventListener('resize', size)
    return () => {
      window.removeEventListener('resize', size)
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [])

  const handleEvent = useCallback((evt: any) => {
    if (evt.type === 'init') {
      setStages(evt.stages)
      stageIdx.current = Object.fromEntries(evt.stages.map((s: StageMeta, i: number) => [s.key, i]))
      const ord: string[] = evt.files.map((f: any) => f.file_id)
      setOrder(ord)
      const init: Record<string, Lane> = {}
      for (const f of evt.files) {
        init[f.file_id] = { fileId: f.file_id, label: f.label, status: {}, reached: 0, detail: 'queued' }
      }
      setLanes(init)
      return
    }
    if (evt.type === 'stage') {
      const idx = stageIdx.current[evt.stage] ?? -1
      setLanes((prev) => {
        const l = prev[evt.file_id]
        if (!l) return prev
        return {
          ...prev,
          [evt.file_id]: {
            ...l,
            status: { ...l.status, [evt.stage]: evt.status },
            reached: idx < 0 ? l.reached : Math.max(l.reached, idx),
            detail: evt.detail || l.detail,
          },
        }
      })
      return
    }
    if (evt.type === 'result') {
      setLanes((prev) => {
        const l = prev[evt.file_id]
        if (!l) return prev
        return {
          ...prev,
          [evt.file_id]: {
            ...l,
            outcome: evt.outcome,
            amount: evt.amount,
            evidence: evt.evidence,
            reason: evt.reason,
            caseNumber: evt.case_number,
            caseSequence: evt.case_sequence,
            deliveryEmail: evt.delivery_email,
            deliveryContact: evt.delivery_contact,
            deliveryRef: evt.delivery_ref,
            deliverySent: evt.delivery_sent,
            detail: evt.reason || l.detail,
          },
        }
      })
      if (evt.outcome === 'AUTO_RECOUP') fireConfetti(evt.file_id)
      return
    }
    if (evt.type === 'done') {
      setTotals({ auto: evt.auto, review: evt.review, recovered: evt.recovered })
      setPhase('done')
    }
  }, [fireConfetti])

  const start = useCallback(async () => {
    if (phase === 'running') return
    try { sessionStorage.removeItem(CACHE_KEY) } catch { /* noop */ }
    setPhase('running'); setTotals(null)
    setLanes({}); setOrder([]); setStages([])
    const { pace, stagger } = SPEEDS[speed]
    const ctrl = new AbortController()
    abortRef.current = ctrl
    try {
      const res = await fetch(`${API_BASE}/demo/run?pace=${pace}&stagger=${stagger}`, {
        credentials: 'include',
        headers: { Accept: 'text/event-stream' },
        signal: ctrl.signal,
      })
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
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
            if (line.startsWith('data: ')) {
              try { handleEvent(JSON.parse(line.slice(6))) } catch { /* ignore */ }
            }
          }
        }
      }
    } catch (e: any) {
      if (e?.name !== 'AbortError') { setPhase('done') }
    }
  }, [phase, speed, handleEvent])

  // Clear the cases this demo created so a re-run reproduces the 5/5 split from a
  // clean slate (no reseed/restart). Wipes the lanes back to the idle prompt.
  const reset = useCallback(async () => {
    if (phase === 'running' || resetting) return
    setResetting(true)
    try {
      await fetch(`${API_BASE}/demo/reset`, { method: 'POST', credentials: 'include' })
    } catch { /* best-effort — nothing to undo */ }
    try { sessionStorage.removeItem(CACHE_KEY) } catch { /* noop */ }
    setResetting(false)
    setPhase('idle'); setTotals(null)
    setLanes({}); setOrder([]); setStages([])
  }, [phase, resetting])

  const liveTxt = phase === 'running' ? 'Running…' : phase === 'done' ? 'Done' : 'Ready'
  const total = order.length || 10

  return (
    <div className="ccr-wrap">
      <style>{STYLES}</style>

      <div className="ccr-inner">
        {/* masthead */}
        <header className="ccr-head">
          <div className="ccr-title">
            <h1>Claims Control Room <span className="ccr-spark">·</span> Live Run</h1>
            <p>
              Ten claims land at once. Robots read, score, and check each one — then{' '}
              <b style={{ color: C.gold }}>finish the easy wins on their own</b> or{' '}
              <b style={{ color: C.human }}>wave a hand for a human</b>.
            </p>
          </div>
          <div className={`ccr-live ${phase === 'running' ? 'on' : ''}`}>
            <span className="ccr-beat" /><span>{liveTxt}</span>
          </div>
        </header>

        {/* HUD */}
        <section className="ccr-hud" aria-label="Run totals">
          <div className="ccr-stat run">
            <span className="ccr-swatch" />
            <div className="ccr-cap">In the machine</div>
            <div className="ccr-num">{hud.run}<span className="ccr-numsuffix"> / {total}</span></div>
            <div className="ccr-sub">claims processing now</div>
          </div>
          <div className="ccr-stat done">
            <span className="ccr-swatch" />
            <div className="ccr-cap">Auto-recouped</div>
            <div className="ccr-num">{hud.auto}</div>
            <div className="ccr-sub">closed with zero clicks</div>
          </div>
          <div className="ccr-stat human">
            <span className="ccr-swatch" />
            <div className="ccr-cap">Needs a human</div>
            <div className="ccr-num">{hud.review}</div>
            <div className="ccr-sub">waiting at the help desk</div>
          </div>
          <div className="ccr-stat cash">
            <span className="ccr-swatch" />
            <div className="ccr-cap">Recovered</div>
            <div className="ccr-num">{money(hud.recovered)}</div>
            <div className="ccr-sub">dollars flagged back</div>
          </div>
        </section>

        {/* progress */}
        <div className="ccr-overall">
          <span>PROGRESS</span>
          <div className="ccr-bar"><i style={{ width: `${progress}%` }} /></div>
          <b>{progress}%</b>
        </div>

        {/* controls */}
        <div className="ccr-controls">
          <button className="ccr-ctl" onClick={start} disabled={phase === 'running' || resetting}>
            {phase === 'running' ? 'Running…' : phase === 'done' ? '↻ Run again' : '▶ Start run'}
          </button>
          <button className="ccr-ctl ghost" onClick={reset} disabled={phase === 'running' || resetting}
            title="Delete the cases this demo created so the next run starts clean">
            {resetting ? 'Clearing…' : '🗑 Clear cases'}
          </button>
          <div className="ccr-speed" role="group" aria-label="Speed">
            {(Object.keys(SPEEDS) as Speed[]).map((s) => (
              <button key={s} onClick={() => { if (phase !== 'running') setSpeed(s) }}
                aria-pressed={speed === s} disabled={phase === 'running'}>{s}</button>
            ))}
          </div>
          <div className="ccr-legend">
            <span><i className="ccr-dotk" style={{ background: C.work }} />working</span>
            <span><i className="ccr-dotk" style={{ background: C.done }} />done</span>
            <span><i className="ccr-dotk" style={{ background: C.gold }} />auto-recouped</span>
            <span><i className="ccr-dotk" style={{ background: C.human }} />needs human</span>
          </div>
        </div>

        {/* board */}
        <div className="ccr-board">
          <div className={`ccr-grid ${phase === 'running' ? 'running' : ''}`}>
            <div className="ccr-row ccr-colhead">
              <div className="ccr-h1c">Claim</div>
              <div className="ccr-stations">
                {stages.map((s) => (
                  <div key={s.key} className="ccr-st">
                    <span className="ccr-ic">{s.emoji}</span>
                    <span className="ccr-lb">{s.label}</span>
                  </div>
                ))}
              </div>
              <div className="ccr-h3c">Result</div>
            </div>

            {order.map((id) => {
              const l = lanes[id]
              if (!l) return null
              return (
                <LaneRow key={id} lane={l} stages={stages} decisionIdx={decisionIdx}
                  registerRow={(el) => { rowRefs.current[id] = el }} />
              )
            })}

            {order.length === 0 && (
              <div className="ccr-empty">
                <div className="ccr-emptybig">▶</div>
                Press <b>Start run</b> to drop 10 claims onto the conveyor. Five clear themselves; five stop for you.
              </div>
            )}
          </div>
        </div>

        {phase === 'done' && totals && (
          <div className="ccr-summary">
            <b style={{ color: C.gold }}>{totals.auto} auto-recouped</b> without a human ·{' '}
            <b style={{ color: C.human }}>{totals.review} routed</b> to review ·{' '}
            <b style={{ color: C.done }}>{money(totals.recovered)}</b> recovered on autopilot.
            {totals.auto > 0 && (
              <div className="ccr-summary-deliv">
                ✉️ Recoupment notices for all {totals.auto} auto-recouped claims were delivered to each
                provider — uploaded to the provider portal and a secure download link emailed to the
                billing contact (see each lane for the address). Full trail in the case Audit History.
              </div>
            )}
          </div>
        )}

        <div className="ccr-foot">
          Live pipeline data · lanes run on staggered timers to mirror{' '}
          <b>one worker thread per file</b> · fork rule: confidence ≥ 0.90 (or excluded-provider hit) auto-recoups, else a human reviews.
        </div>
      </div>

      <canvas className="ccr-confetti" ref={canvasRef} />
    </div>
  )
}

function LaneRow({ lane, stages, decisionIdx, registerRow }: {
  lane: Lane; stages: StageMeta[]; decisionIdx: number; registerRow: (el: HTMLDivElement | null) => void
}) {
  const n = stages.length
  // Node geometry: stations sit at (i+0.5)/n across the track. Inset the rail to
  // the first/last node centres (Q) so the dashes run circle-to-circle; the solid
  // fill covers the dashes up to the furthest station reached.
  const Q = n > 0 ? 100 / (2 * n) : 0
  const nodeAt = (i: number) => (n > 1 ? Q + (i / (n - 1)) * (100 - 2 * Q) : Q)
  const fillTo = (i: number) => (n > 1 ? (i / (n - 1)) * (100 - 2 * Q) : 0)

  const started = Object.keys(lane.status).length > 0 || !!lane.outcome
  const state =
    lane.outcome === 'REVIEW' ? 'review' :
    lane.outcome === 'AUTO_RECOUP' ? 'done' :
    started ? 'run' : 'idle'

  const chipLabel = lane.caseNumber
    ? lane.caseNumber.replace(/^.*[-\s]/, '')
    : lane.label.slice(0, 6)

  return (
    <div ref={registerRow}
      className={`ccr-row ccr-lane ${state === 'idle' ? 'idle' : ''} ${state === 'review' ? 'review' : ''} ${state === 'done' ? 'done' : ''}`}>
      <div className="ccr-who">
        <div className="ccr-nm">{lane.label}</div>
        <div className="ccr-meta">
          {lane.caseNumber && lane.caseSequence != null ? (
            <>
              <Link className="ccr-caselink" to={`/cases/${lane.caseSequence}`}
                title={`Open case ${lane.caseNumber}`}>{lane.caseNumber}</Link>
              {' · '}
            </>
          ) : lane.caseNumber ? `${lane.caseNumber} · ` : ''}
          {lane.detail}
        </div>
      </div>

      <div className="ccr-track">
        <div className="ccr-trail" style={{ left: `${Q}%`, right: `${Q}%` }} />
        <div className="ccr-fill" style={{ left: `${Q}%`, width: `${fillTo(lane.reached)}%` }} />
        <div className="ccr-dots">
          {stages.map((s, i) => {
            let cls = 'ccr-dot'
            if (lane.outcome === 'REVIEW') {
              if (i < decisionIdx) cls += ' done'
              else if (i === decisionIdx) cls += ' human'
            } else if (lane.outcome === 'AUTO_RECOUP' || lane.outcome === 'CLEAN') {
              cls += ' done'
            } else {
              const st = lane.status[s.key]
              if (st === 'done') cls += ' done'
              else if (st === 'active') cls += ' active'
              else if (st === 'error') cls += ' err'
              else if (i < lane.reached) cls += ' done'
            }
            return <div key={s.key} className={cls} />
          })}
        </div>
        <div className="ccr-chip" style={{ left: `${nodeAt(lane.reached)}%` }}>
          <span>📄</span><span>{chipLabel}</span>
        </div>
      </div>

      <div className="ccr-result" title={lane.reason || undefined}>
        {!lane.outcome && !started && <span className="ccr-badge b-idle">queued</span>}
        {!lane.outcome && started && <span className="ccr-badge b-run">processing…</span>}
        {lane.outcome === 'REVIEW' && (
          <span className="ccr-badge b-review">🙋 needs analyst{lane.evidence != null ? ` · ${lane.evidence.toFixed(2)}` : ''}</span>
        )}
        {lane.outcome === 'AUTO_RECOUP' && (
          <>
            <span className="ccr-badge b-done">✅ recouped</span>
            <span className="ccr-amt">{money(lane.amount || 0)}</span>
            {lane.deliveryEmail && (
              <span className={`ccr-deliv ${lane.deliverySent ? 'real' : 'sim'}`}
                title={`Recoupment notice delivered to the provider — uploaded to the provider portal and a secure download link ${lane.deliverySent ? 'emailed' : 'emailed (simulated — EmailJS not configured)'} to ${lane.deliveryContact || 'the billing contact'} <${lane.deliveryEmail}>${lane.deliveryRef ? `. Confirmation ${lane.deliveryRef}.` : '.'}`}>
                <span className="ccr-deliv-hd">{lane.deliverySent ? '✉️ email sent' : '✉️ notice sent (sim)'}</span>
                <span className="ccr-deliv-to">{lane.deliveryEmail}</span>
              </span>
            )}
          </>
        )}
        {lane.outcome === 'CLEAN' && <span className="ccr-badge b-idle">— no issue</span>}
        {lane.outcome === 'ERROR' && <span className="ccr-badge b-err">! error</span>}
      </div>
    </div>
  )
}

const STYLES = `
/* The page background stays the app's light gray (bg-gray-100, from the layout);
   the dark "control room" now lives inside a self-contained rounded board that
   floats on it — same gray-page + card pattern as Case Details et al. */
.ccr-wrap {
  font-family:"Baloo 2","Nunito",ui-rounded,"SF Pro Rounded",system-ui,-apple-system,sans-serif;
  color:${C.ink};
  min-height:100%; line-height:1.4; position:relative;
}
.ccr-inner {
  max-width:1180px; margin:0 auto; display:flex; flex-direction:column; gap:20px;
  background:linear-gradient(180deg, ${C.ground}, ${C.ground2});
  border:1px solid ${C.line}; border-radius:16px;
  padding:clamp(18px,3vw,32px);
  box-shadow:0 1px 3px rgba(16,24,40,.06), 0 12px 32px rgba(16,24,40,.05);
}

.ccr-head { display:flex; flex-wrap:wrap; align-items:flex-end; gap:16px 24px; justify-content:space-between; }
.ccr-title h1 { margin:0; font-size:clamp(26px,4vw,40px); font-weight:800; letter-spacing:-.02em; text-wrap:balance; }
.ccr-title h1 .ccr-spark { color:${C.work}; }
.ccr-title p { margin:6px 0 0; color:${C.dim}; font-size:15px; max-width:52ch; }
.ccr-live { display:inline-flex; align-items:center; gap:8px; font-family:ui-monospace,"SF Mono",Menlo,monospace;
  font-size:12px; text-transform:uppercase; letter-spacing:.14em; color:${C.dim};
  padding:6px 12px; border:1px solid ${C.line}; border-radius:999px; background:${C.panel2}; }
.ccr-beat { width:9px; height:9px; border-radius:50%; background:${C.faint}; }
.ccr-live.on .ccr-beat { background:${C.done}; box-shadow:0 0 0 0 #16a34a66; animation:ccrbeat 1.1s infinite; }
@keyframes ccrbeat { 70%{ box-shadow:0 0 0 8px #16a34a00; } 100%{ box-shadow:0 0 0 0 #16a34a00; } }

.ccr-hud { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; }
.ccr-stat { background:${C.panel2}; border:1px solid ${C.line};
  border-radius:14px; padding:16px 18px; position:relative; overflow:hidden; }
.ccr-cap { font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; text-transform:uppercase; letter-spacing:.13em; color:${C.dim}; }
.ccr-num { font-family:ui-monospace,"SF Mono",Menlo,monospace; font-variant-numeric:tabular-nums; font-weight:700;
  font-size:clamp(24px,3.4vw,36px); margin-top:4px; line-height:1; }
.ccr-numsuffix { color:${C.faint}; font-size:.5em; }
.ccr-sub { font-size:12px; color:${C.faint}; margin-top:6px; }
.ccr-stat.done .ccr-num { color:${C.done}; }
.ccr-stat.human .ccr-num { color:${C.human}; }
.ccr-stat.cash .ccr-num { color:${C.gold}; }
.ccr-swatch { position:absolute; top:0; left:0; bottom:0; width:5px; }
.ccr-stat.done .ccr-swatch { background:${C.done}; }
.ccr-stat.human .ccr-swatch { background:${C.human}; }
.ccr-stat.cash .ccr-swatch { background:${C.gold}; }
.ccr-stat.run .ccr-swatch { background:${C.work}; }

.ccr-overall { display:flex; align-items:center; gap:14px; font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:12px; color:${C.dim}; }
.ccr-bar { flex:1; height:12px; border-radius:999px; background:#eef1f5; border:1px solid ${C.line}; overflow:hidden; }
.ccr-bar > i { display:block; height:100%; width:0; border-radius:999px;
  background:linear-gradient(90deg, ${C.work}, ${C.done}); transition:width .4s ease; }
.ccr-overall b { color:${C.ink}; font-variant-numeric:tabular-nums; }

.ccr-controls { display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
.ccr-ctl { font-family:inherit; font-weight:700; font-size:15px; color:#fff;
  background:${C.brand}; border:none; border-radius:12px;
  padding:11px 20px; cursor:pointer; box-shadow:0 6px 16px #fe017d33; transition:transform .1s, filter .1s; }
.ccr-ctl.ghost { background:${C.panel}; color:${C.ink}; box-shadow:none; border:1px solid ${C.line}; }
.ccr-ctl.ghost:hover:not(:disabled) { background:${C.panel2}; }
.ccr-ctl:hover:not(:disabled) { filter:brightness(1.04); }
.ccr-ctl:active:not(:disabled) { transform:translateY(1px); }
.ccr-ctl:disabled { opacity:.45; cursor:not-allowed; filter:none; transform:none; }
.ccr-speed { display:inline-flex; border:1px solid ${C.line}; border-radius:12px; overflow:hidden; font-family:ui-monospace,"SF Mono",Menlo,monospace; }
.ccr-speed button { background:${C.panel}; color:${C.dim}; border:none; padding:10px 14px; cursor:pointer; font-size:13px; }
.ccr-speed button[aria-pressed="true"] { background:#f3f4f6; color:${C.ink}; }
.ccr-speed button:disabled { cursor:default; }
.ccr-legend { margin-left:auto; display:flex; gap:16px; flex-wrap:wrap; font-size:13px; color:${C.dim}; }
.ccr-legend span { display:inline-flex; align-items:center; gap:7px; }
.ccr-dotk { width:11px; height:11px; border-radius:50%; }

.ccr-board { background:${C.panel}; border:1px solid ${C.line}; border-radius:20px; padding:10px 10px 14px; overflow-x:auto; }
.ccr-grid { min-width:820px; display:flex; flex-direction:column; }
.ccr-row { display:grid; grid-template-columns:210px minmax(360px,1fr) 158px; align-items:center; gap:12px; }
.ccr-colhead { position:sticky; top:0; padding:8px 8px 12px; border-bottom:1px solid ${C.line}; margin-bottom:6px; background:${C.panel}; z-index:2; }
.ccr-stations { display:grid; grid-template-columns:repeat(9,1fr); }
.ccr-st { display:flex; flex-direction:column; align-items:center; gap:4px; text-align:center; }
.ccr-st .ccr-ic { font-size:18px; line-height:1; }
.ccr-st .ccr-lb { font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:9.5px; text-transform:uppercase; letter-spacing:.04em; color:${C.faint}; }
.ccr-h1c { font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:${C.dim}; align-self:end; }
.ccr-h3c { font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:${C.dim}; text-align:right; align-self:end; }

.ccr-lane { padding:9px 8px; border-radius:12px; }
.ccr-lane + .ccr-lane { border-top:1px solid #f3f4f6; }
.ccr-lane:hover { background:#f9fafb; }
.ccr-who .ccr-nm { font-weight:700; font-size:15px; line-height:1.15; }
.ccr-who .ccr-meta { font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; color:${C.dim}; margin-top:2px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ccr-caselink { color:${C.brand}; text-decoration:none; font-weight:700; border-bottom:1px dotted ${C.brand}66; }
.ccr-caselink:hover { color:#c2015f; border-bottom-color:#c2015f; }

.ccr-track { position:relative; height:34px; }
.ccr-trail { position:absolute; top:50%; height:2px; transform:translateY(-50%);
  background:repeating-linear-gradient(90deg, #d1d5db 0 6px, transparent 6px 13px); background-size:13px 100%; }
.ccr-grid.running .ccr-trail { animation:ccrmarch .6s linear infinite; }
@keyframes ccrmarch { to { background-position:-13px 0; } }
.ccr-fill { position:absolute; top:50%; height:3px; transform:translateY(-50%); border-radius:2px;
  background:linear-gradient(90deg, ${C.done}, ${C.work}); box-shadow:0 0 6px #2563eb2e; transition:width .5s ease; }
.ccr-lane.review .ccr-fill { background:linear-gradient(90deg, ${C.done}, ${C.human}); box-shadow:0 0 6px #ea580c2e; }
.ccr-lane.done .ccr-fill { background:linear-gradient(90deg, ${C.done}, ${C.gold}); box-shadow:0 0 6px #d977062e; }

.ccr-dots { position:absolute; inset:0; display:grid; grid-template-columns:repeat(9,1fr); align-items:center; }
.ccr-dot { justify-self:center; width:14px; height:14px; border-radius:50%; background:${C.ground2};
  border:2px solid ${C.line}; transition:background .25s, border-color .25s, box-shadow .25s;
  display:grid; place-items:center; font-size:8px; color:${C.ground2}; font-weight:900; }
.ccr-dot.done { background:${C.done}; border-color:${C.done}; }
.ccr-dot.done::after { content:"✓"; }
.ccr-dot.active { background:${C.work}; border-color:${C.work}; box-shadow:0 0 0 0 #2563ebaa; animation:ccrpulse 1s infinite; }
.ccr-dot.human { background:${C.human}; border-color:${C.human}; box-shadow:0 0 10px #ea580c66; }
.ccr-dot.human::after { content:"!"; }
.ccr-dot.err { background:${C.red}; border-color:${C.red}; }
@keyframes ccrpulse { 70%{ box-shadow:0 0 0 6px #2563eb00; } 100%{ box-shadow:0 0 0 0 #2563eb00; } }

.ccr-chip { position:absolute; top:50%; transform:translate(-50%,-50%); height:24px; padding:0 9px; border-radius:8px;
  display:flex; align-items:center; gap:5px; background:#ffffff; border:1px solid ${C.line}; color:${C.ink};
  font-weight:800; font-size:11px; font-family:ui-monospace,"SF Mono",Menlo,monospace; box-shadow:0 2px 8px rgba(16,24,40,.14);
  transition:left .5s cubic-bezier(.5,.05,.3,1); white-space:nowrap; z-index:3; }
.ccr-lane.review .ccr-chip { background:linear-gradient(180deg, #ffedd5, ${C.human}); border-color:${C.human}; color:#fff; }
.ccr-lane.done .ccr-chip { background:linear-gradient(180deg, #fde68a, ${C.gold}); border-color:${C.gold}; color:#fff; }
.ccr-lane.idle .ccr-chip { opacity:0; }

.ccr-result { text-align:right; font-family:ui-monospace,"SF Mono",Menlo,monospace; }
.ccr-badge { display:inline-block; padding:4px 10px; border-radius:8px; font-size:12px; font-weight:700; letter-spacing:.02em; }
.ccr-amt { display:block; font-size:15px; font-weight:700; color:${C.gold}; margin-top:3px; font-variant-numeric:tabular-nums; }
/* Delivery receipt on an auto-recouped lane — the plain "yes, the provider was
   actually contacted" confirmation, with the email address as the reference. */
.ccr-deliv { display:inline-flex; flex-direction:column; align-items:flex-end; gap:1px; margin-top:5px;
  padding:4px 8px; border:1px solid ${C.line}; border-radius:8px; cursor:default; max-width:100%; }
.ccr-deliv.real { border-color:#bbf7d0; background:#f0fdf4; }   /* real EmailJS send */
.ccr-deliv.sim  { border-color:#fde68a; background:#fffbeb; }   /* simulated */
.ccr-deliv-hd { font-size:10px; font-weight:800; letter-spacing:.04em; text-transform:uppercase; }
.ccr-deliv.real .ccr-deliv-hd { color:#15803d; }
.ccr-deliv.sim  .ccr-deliv-hd { color:#b45309; }
.ccr-deliv-to { font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; color:${C.dim};
  max-width:100%; overflow:hidden; text-overflow:ellipsis; }
.b-idle { background:#f3f4f6; color:${C.dim}; }
.b-run { background:#eff6ff; color:#1d4ed8; border:1px solid #dbeafe; }
.b-review { background:#fff7ed; color:#c2410c; border:1px solid #fed7aa; }
.b-done { background:#f0fdf4; color:#15803d; border:1px solid #bbf7d0; }
.b-err { background:#fef2f2; color:#b91c1c; border:1px solid #fecaca; }

.ccr-empty { text-align:center; color:${C.dim}; padding:70px 20px; font-size:15px; }
.ccr-emptybig { font-size:44px; color:${C.work}; margin-bottom:14px; opacity:.6; }
.ccr-summary { background:${C.panel}; border:1px solid ${C.line}; border-radius:14px; padding:16px 20px; font-size:15px; text-align:center; }
.ccr-summary-deliv { margin-top:10px; padding-top:10px; border-top:1px solid ${C.line};
  font-size:13px; line-height:1.5; color:${C.dim}; max-width:70ch; margin-left:auto; margin-right:auto; }
.ccr-foot { color:${C.faint}; font-size:12.5px; text-align:center; font-family:ui-monospace,"SF Mono",Menlo,monospace; }
.ccr-foot b { color:${C.dim}; }

.ccr-confetti { position:fixed; inset:0; pointer-events:none; z-index:50; }

@media (max-width:640px){
  .ccr-hud { grid-template-columns:repeat(2,1fr); }
  .ccr-legend { width:100%; margin-left:0; }
}
@media (prefers-reduced-motion: reduce){
  .ccr-wrap *{ animation:none !important; transition-duration:.001ms !important; }
}
`
