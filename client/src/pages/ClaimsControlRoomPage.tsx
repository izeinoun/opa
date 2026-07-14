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
import { API_BASE } from '../services/api'

// ── palette (the control-room state machine) ──────────────────────────────
const C = {
  ground: '#0d1030',
  ground2: '#0a0c24',
  panel: '#191d45',
  panel2: '#20265c',
  line: '#2b3170',
  ink: '#eef0ff',
  dim: '#9aa0d4',
  faint: '#6a70a8',
  idle: '#3b427e',
  work: '#29d3ec',  // cyan  — a station is running
  done: '#34e6a4',  // mint  — a station finished
  gold: '#ffca3a',  // auto-recouped, no human
  human: '#ff8f4d', // needs a human
  red: '#ff5d6c',
}
const CONFETTI_COLORS = ['#ffca3a', '#34e6a4', '#29d3ec', '#ff8f4d', '#eef0ff']

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

export default function ClaimsControlRoomPage() {
  const [stages, setStages] = useState<StageMeta[]>([])
  const [lanes, setLanes] = useState<Record<string, Lane>>({})
  const [order, setOrder] = useState<string[]>([])
  const [phase, setPhase] = useState<'idle' | 'running' | 'done'>('idle')
  const [speed, setSpeed] = useState<Speed>('1×')
  const [totals, setTotals] = useState<{ auto: number; review: number; recovered: number } | null>(null)
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
        <div className="ccr-meta">{lane.caseNumber ? `${lane.caseNumber} · ` : ''}{lane.detail}</div>
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
          </>
        )}
        {lane.outcome === 'CLEAN' && <span className="ccr-badge b-idle">— no issue</span>}
        {lane.outcome === 'ERROR' && <span className="ccr-badge b-err">! error</span>}
      </div>
    </div>
  )
}

const STYLES = `
.ccr-wrap {
  font-family:"Baloo 2","Nunito",ui-rounded,"SF Pro Rounded",system-ui,-apple-system,sans-serif;
  color:${C.ink};
  background:
    radial-gradient(1200px 600px at 85% -10%, #23306b55, transparent 60%),
    radial-gradient(900px 500px at 0% 110%, #3a1f5e40, transparent 55%),
    linear-gradient(180deg, ${C.ground}, ${C.ground2});
  min-height:100%; padding:clamp(16px,3vw,34px); line-height:1.4; position:relative; overflow:hidden;
}
.ccr-inner { max-width:1180px; margin:0 auto; display:flex; flex-direction:column; gap:20px; }

.ccr-head { display:flex; flex-wrap:wrap; align-items:flex-end; gap:16px 24px; justify-content:space-between; }
.ccr-title h1 { margin:0; font-size:clamp(26px,4vw,40px); font-weight:800; letter-spacing:-.02em; text-wrap:balance; }
.ccr-title h1 .ccr-spark { color:${C.work}; }
.ccr-title p { margin:6px 0 0; color:${C.dim}; font-size:15px; max-width:52ch; }
.ccr-live { display:inline-flex; align-items:center; gap:8px; font-family:ui-monospace,"SF Mono",Menlo,monospace;
  font-size:12px; text-transform:uppercase; letter-spacing:.14em; color:${C.dim};
  padding:6px 12px; border:1px solid ${C.line}; border-radius:999px; background:#ffffff08; }
.ccr-beat { width:9px; height:9px; border-radius:50%; background:${C.faint}; }
.ccr-live.on .ccr-beat { background:${C.done}; box-shadow:0 0 0 0 #34e6a4aa; animation:ccrbeat 1.1s infinite; }
@keyframes ccrbeat { 70%{ box-shadow:0 0 0 8px #34e6a400; } 100%{ box-shadow:0 0 0 0 #34e6a400; } }

.ccr-hud { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; }
.ccr-stat { background:linear-gradient(180deg, ${C.panel}, #141838); border:1px solid ${C.line};
  border-radius:18px; padding:16px 18px; position:relative; overflow:hidden; }
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
.ccr-bar { flex:1; height:12px; border-radius:999px; background:#0c0f2b; border:1px solid ${C.line}; overflow:hidden; }
.ccr-bar > i { display:block; height:100%; width:0; border-radius:999px;
  background:linear-gradient(90deg, ${C.work}, ${C.done}); transition:width .4s ease; }
.ccr-overall b { color:${C.ink}; font-variant-numeric:tabular-nums; }

.ccr-controls { display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
.ccr-ctl { font-family:inherit; font-weight:700; font-size:15px; color:${C.ground2};
  background:linear-gradient(180deg, #5df0ff, ${C.work}); border:none; border-radius:12px;
  padding:11px 20px; cursor:pointer; box-shadow:0 6px 18px #29d3ec33; transition:transform .1s, filter .1s; }
.ccr-ctl.ghost { background:#ffffff0f; color:${C.ink}; box-shadow:none; border:1px solid ${C.line}; }
.ccr-ctl:hover:not(:disabled) { filter:brightness(1.06); }
.ccr-ctl:active:not(:disabled) { transform:translateY(1px); }
.ccr-ctl:disabled { opacity:.45; cursor:not-allowed; filter:none; transform:none; }
.ccr-speed { display:inline-flex; border:1px solid ${C.line}; border-radius:12px; overflow:hidden; font-family:ui-monospace,"SF Mono",Menlo,monospace; }
.ccr-speed button { background:transparent; color:${C.dim}; border:none; padding:10px 14px; cursor:pointer; font-size:13px; }
.ccr-speed button[aria-pressed="true"] { background:#ffffff12; color:${C.ink}; }
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
.ccr-lane + .ccr-lane { border-top:1px solid #ffffff08; }
.ccr-lane:hover { background:#ffffff06; }
.ccr-who .ccr-nm { font-weight:700; font-size:15px; line-height:1.15; }
.ccr-who .ccr-meta { font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; color:${C.dim}; margin-top:2px;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }

.ccr-track { position:relative; height:34px; }
.ccr-trail { position:absolute; top:50%; height:2px; transform:translateY(-50%);
  background:repeating-linear-gradient(90deg, ${C.line} 0 6px, transparent 6px 13px); background-size:13px 100%; }
.ccr-grid.running .ccr-trail { animation:ccrmarch .6s linear infinite; }
@keyframes ccrmarch { to { background-position:-13px 0; } }
.ccr-fill { position:absolute; top:50%; height:3px; transform:translateY(-50%); border-radius:2px;
  background:linear-gradient(90deg, ${C.done}, ${C.work}); box-shadow:0 0 8px #29d3ec66; transition:width .5s ease; }
.ccr-lane.review .ccr-fill { background:linear-gradient(90deg, ${C.done}, ${C.human}); box-shadow:0 0 8px #ff8f4d66; }
.ccr-lane.done .ccr-fill { background:linear-gradient(90deg, ${C.done}, ${C.gold}); box-shadow:0 0 8px #ffca3a66; }

.ccr-dots { position:absolute; inset:0; display:grid; grid-template-columns:repeat(9,1fr); align-items:center; }
.ccr-dot { justify-self:center; width:14px; height:14px; border-radius:50%; background:${C.ground2};
  border:2px solid ${C.line}; transition:background .25s, border-color .25s, box-shadow .25s;
  display:grid; place-items:center; font-size:8px; color:${C.ground2}; font-weight:900; }
.ccr-dot.done { background:${C.done}; border-color:${C.done}; }
.ccr-dot.done::after { content:"✓"; }
.ccr-dot.active { background:${C.work}; border-color:${C.work}; box-shadow:0 0 0 0 #29d3ecaa; animation:ccrpulse 1s infinite; }
.ccr-dot.human { background:${C.human}; border-color:${C.human}; box-shadow:0 0 12px #ff8f4d99; }
.ccr-dot.human::after { content:"!"; }
.ccr-dot.err { background:${C.red}; border-color:${C.red}; }
@keyframes ccrpulse { 70%{ box-shadow:0 0 0 6px #29d3ec00; } 100%{ box-shadow:0 0 0 0 #29d3ec00; } }

.ccr-chip { position:absolute; top:50%; transform:translate(-50%,-50%); height:24px; padding:0 9px; border-radius:8px;
  display:flex; align-items:center; gap:5px; background:linear-gradient(180deg, #fff, #dfe4ff); color:#141838;
  font-weight:800; font-size:11px; font-family:ui-monospace,"SF Mono",Menlo,monospace; box-shadow:0 4px 12px #0008;
  transition:left .5s cubic-bezier(.5,.05,.3,1); white-space:nowrap; z-index:3; }
.ccr-lane.review .ccr-chip { background:linear-gradient(180deg, #ffd9b8, ${C.human}); color:#3a1c05; }
.ccr-lane.done .ccr-chip { background:linear-gradient(180deg, #fff0bf, ${C.gold}); color:#3a2e00; }
.ccr-lane.idle .ccr-chip { opacity:0; }

.ccr-result { text-align:right; font-family:ui-monospace,"SF Mono",Menlo,monospace; }
.ccr-badge { display:inline-block; padding:4px 10px; border-radius:8px; font-size:12px; font-weight:700; letter-spacing:.02em; }
.ccr-amt { display:block; font-size:15px; font-weight:700; color:${C.gold}; margin-top:3px; font-variant-numeric:tabular-nums; }
.b-idle { background:#ffffff10; color:${C.faint}; }
.b-run { background:#29d3ec22; color:${C.work}; }
.b-review { background:#ff8f4d22; color:${C.human}; }
.b-done { background:#34e6a422; color:${C.done}; }
.b-err { background:#ff5d6c22; color:${C.red}; }

.ccr-empty { text-align:center; color:${C.dim}; padding:70px 20px; font-size:15px; }
.ccr-emptybig { font-size:44px; color:${C.work}; margin-bottom:14px; opacity:.6; }
.ccr-summary { background:${C.panel}; border:1px solid ${C.line}; border-radius:14px; padding:16px 20px; font-size:15px; text-align:center; }
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
