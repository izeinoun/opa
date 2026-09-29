// SpotlightTour — the shared renderer for the new-user walkthrough.
//
// Reusable across every SPA: it reads the tour from useTour(), finds the DOM
// element carrying data-tour="<anchor>", cuts a spotlight hole around it, and
// floats a tooltip beside it. Missing anchors (a step whose element isn't on
// this page yet, or an app that never added the attribute) degrade gracefully
// to a centered card, so the tour never breaks — it just gets less pointy.
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useLocation, useNavigate } from 'react-router-dom'
import { X, ArrowLeft, ArrowRight } from 'lucide-react'
import { appUrl, type AppKey } from '../../config/appUrls'
import { useTour } from './useTour'

type Rect = { top: number; left: number; width: number; height: number }

const RING_PAD = 6          // px of breathing room around the highlighted element
const CARD_W = 340
const GAP = 14              // px between the spotlight and the tooltip
const MARGIN = 12           // min distance from any viewport edge

/** Locate the anchored element, retrying briefly while it mounts/animates in. */
function useAnchorRect(anchor: string | null | undefined, stepKey: string): Rect | null {
  const [rect, setRect] = useState<Rect | null>(null)

  const measure = useCallback(() => {
    if (!anchor) { setRect(null); return false }
    const el = document.querySelector<HTMLElement>(`[data-tour="${anchor}"]`)
    if (!el) { setRect(null); return false }
    const r = el.getBoundingClientRect()
    if (r.width === 0 && r.height === 0) { setRect(null); return false }
    setRect({ top: r.top, left: r.left, width: r.width, height: r.height })
    return true
  }, [anchor])

  // Poll for up to ~1.5s so the element has time to appear after a route change
  // or the nav expanding. Stop as soon as we find it.
  useLayoutEffect(() => {
    let raf = 0
    let tries = 0
    const el = anchor ? document.querySelector<HTMLElement>(`[data-tour="${anchor}"]`) : null
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    const tick = () => {
      const found = measure()
      tries += 1
      if (!found && tries < 90) raf = requestAnimationFrame(tick)
    }
    tick()
    return () => cancelAnimationFrame(raf)
    // stepKey forces a fresh hunt on every step, even if anchor repeats.
  }, [anchor, stepKey, measure])

  // Keep the hole glued to the element as the page scrolls/resizes.
  useEffect(() => {
    if (!anchor) return
    const onMove = () => measure()
    window.addEventListener('scroll', onMove, true)
    window.addEventListener('resize', onMove)
    return () => {
      window.removeEventListener('scroll', onMove, true)
      window.removeEventListener('resize', onMove)
    }
  }, [anchor, measure])

  return rect
}

/** Position the tooltip card near the hole, clamped to the viewport. */
function placeCard(rect: Rect | null, placement: string | undefined): { top: number; left: number } {
  const vw = window.innerWidth
  const vh = window.innerHeight
  if (!rect) {
    return { top: Math.max(MARGIN, vh / 2 - 120), left: Math.max(MARGIN, vw / 2 - CARD_W / 2) }
  }
  const spaceBelow = vh - (rect.top + rect.height)
  const spaceRight = vw - (rect.left + rect.width)
  let side = placement && placement !== 'auto' ? placement : ''
  if (!side || side === 'center') {
    if (spaceRight > CARD_W + GAP + MARGIN) side = 'right'
    else if (spaceBelow > 200) side = 'bottom'
    else if (rect.top > 200) side = 'top'
    else side = 'right'
  }

  let top = rect.top
  let left = rect.left
  switch (side) {
    case 'right':  top = rect.top; left = rect.left + rect.width + GAP; break
    case 'left':   top = rect.top; left = rect.left - CARD_W - GAP; break
    case 'top':    top = rect.top - GAP - 160; left = rect.left; break
    case 'bottom':
    default:       top = rect.top + rect.height + GAP; left = rect.left; break
  }
  // Clamp inside the viewport.
  left = Math.min(Math.max(MARGIN, left), vw - CARD_W - MARGIN)
  top = Math.min(Math.max(MARGIN, top), vh - 180 - MARGIN)
  return { top, left }
}

export default function SpotlightTour() {
  const { tour, current, index, isActive, next, back, skip } = useTour()
  const navigate = useNavigate()
  const location = useLocation()
  const lastRoute = useRef<string | null>(null)

  // Navigate to the step's route before we try to anchor onto it.
  useEffect(() => {
    if (!current?.route) return
    const here = location.pathname + location.search
    if (here !== current.route && lastRoute.current !== current.route) {
      lastRoute.current = current.route
      navigate(current.route)
    }
  }, [current, location, navigate])

  const rect = useAnchorRect(current?.anchor, current?.key ?? '')

  // Escape dismisses the tour.
  useEffect(() => {
    if (!isActive) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') skip()
      if (e.key === 'ArrowRight') next()
      if (e.key === 'ArrowLeft') back()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isActive, skip, next, back])

  if (!isActive || !current || !tour) return null

  const total = tour.steps.length
  const isLast = index === total - 1
  const isFirst = index === 0
  const card = placeCard(rect, current.placement)

  return createPortal(
    <div className="fixed inset-0 z-[9998]" aria-live="polite" role="dialog" aria-modal="true">
      {/* Click catcher — blocks interaction with the page behind the tour. */}
      <div className="absolute inset-0" onClick={(e) => e.stopPropagation()} />

      {/* Dim + spotlight. With an anchor, a giant box-shadow dims everything
          except the hole; without one, a plain full-screen scrim. */}
      {rect ? (
        <div
          className="absolute rounded-xl transition-all duration-300 ease-out pointer-events-none"
          style={{
            top: rect.top - RING_PAD,
            left: rect.left - RING_PAD,
            width: rect.width + RING_PAD * 2,
            height: rect.height + RING_PAD * 2,
            boxShadow: '0 0 0 9999px rgba(15, 23, 42, 0.55)',
            outline: '2px solid rgba(254, 1, 125, 0.9)',
          }}
        />
      ) : (
        <div className="absolute inset-0 bg-slate-900/55 pointer-events-none" />
      )}

      {/* Tooltip card */}
      <div
        className="absolute pointer-events-auto bg-white rounded-2xl shadow-2xl border border-slate-200
                   p-4 flex flex-col gap-2"
        style={{ top: card.top, left: card.left, width: CARD_W }}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-[#FE017D]">
              {tour.role_label} tour
            </span>
            <span className="text-[10px] text-slate-400">· {index + 1} of {total}</span>
          </div>
          <button
            onClick={skip}
            className="text-slate-400 hover:text-slate-600 -mt-1 -mr-1 p-1"
            aria-label="Close tour"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <h3 className="text-sm font-semibold text-slate-900 leading-snug">{current.title}</h3>
        <p className="text-[13px] text-slate-600 leading-relaxed">{current.body}</p>

        {/* Cross-app deep links (outro step). */}
        {current.app_links && current.app_links.length > 0 && (
          <div className="flex flex-col gap-1.5 mt-1">
            {current.app_links.map((l) => (
              <a
                key={l.app}
                href={appUrl(l.app as AppKey, l.path)}
                className="text-[12px] font-medium text-[#FE017D] hover:underline flex items-center gap-1"
              >
                <ArrowRight className="w-3 h-3" /> {l.label}
              </a>
            ))}
          </div>
        )}

        {/* Progress dots */}
        <div className="flex items-center gap-1 mt-1">
          {tour.steps.map((s, i) => (
            <span
              key={s.key}
              className={`h-1 rounded-full transition-all ${
                i === index ? 'w-4 bg-[#FE017D]' : 'w-1.5 bg-slate-200'
              }`}
            />
          ))}
        </div>

        {/* Controls */}
        <div className="flex items-center justify-between mt-1.5">
          <button
            onClick={skip}
            className="text-[12px] text-slate-400 hover:text-slate-600"
          >
            Skip
          </button>
          <div className="flex items-center gap-2">
            {!isFirst && (
              <button
                onClick={back}
                className="flex items-center gap-1 text-[12px] font-medium text-slate-600
                           hover:text-slate-900 px-2.5 py-1.5 rounded-lg hover:bg-slate-100"
              >
                <ArrowLeft className="w-3.5 h-3.5" /> Back
              </button>
            )}
            <button
              onClick={next}
              className="flex items-center gap-1 text-[12px] font-semibold text-white
                         bg-[#FE017D] hover:bg-[#d80169] px-3 py-1.5 rounded-lg"
            >
              {isLast ? 'Done' : 'Next'}
              {!isLast && <ArrowRight className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}
