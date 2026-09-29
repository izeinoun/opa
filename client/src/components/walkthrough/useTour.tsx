// useTour — fetches the role-tailored tour for the current app and manages
// which step is showing. Auto-starts once per user until they finish/skip that
// tour version; re-launchable from the Help (?) button via start().
//
// This provider + the SpotlightTour renderer are the ONE reusable engine every
// SPA embeds; only the data-tour anchors differ per app. See
// server/app/services/walkthrough_service.py for the content.
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, ReactNode,
} from 'react'
import api from '../../services/api'
import type { Tour, TourStep } from './types'

interface TourContextValue {
  tour: Tour | null
  index: number
  isActive: boolean
  current: TourStep | null
  start: () => void
  next: () => void
  back: () => void
  goTo: (i: number) => void
  finish: () => void       // completed — records the version so it won't auto-show again
  skip: () => void         // dismissed — same persistence, different intent
  available: boolean       // a tour was fetched and has steps
}

const Ctx = createContext<TourContextValue | null>(null)

const doneKey = (app: string) => `opa_tour_done_${app}`

export function TourProvider({ app, children }: { app: string; children: ReactNode }) {
  const [tour, setTour] = useState<Tour | null>(null)
  const [index, setIndex] = useState(0)
  const [isActive, setIsActive] = useState(false)
  const autoTried = useRef(false)

  // Fetch the tailored tour once. Failures are silent — the tour is a nicety,
  // never a blocker.
  useEffect(() => {
    let cancelled = false
    api
      .get<Tour>('/walkthrough', { params: { app } })
      .then((res) => { if (!cancelled) setTour(res.data) })
      .catch(() => { /* no tour, no problem */ })
    return () => { cancelled = true }
  }, [app])

  // Auto-start for a first-time viewer of this tour version.
  useEffect(() => {
    if (!tour || !tour.steps.length || autoTried.current) return
    autoTried.current = true
    const doneVersion = Number(localStorage.getItem(doneKey(app)) ?? '0')
    if (doneVersion < tour.version) {
      setIndex(0)
      setIsActive(true)
    }
  }, [tour, app])

  const markDone = useCallback(() => {
    if (tour) localStorage.setItem(doneKey(app), String(tour.version))
  }, [tour, app])

  const start = useCallback(() => { setIndex(0); setIsActive(true) }, [])
  const goTo = useCallback((i: number) => setIndex(i), [])

  const finish = useCallback(() => { setIsActive(false); markDone() }, [markDone])
  const skip = finish

  const next = useCallback(() => {
    setIndex((i) => {
      if (!tour) return i
      if (i >= tour.steps.length - 1) { setIsActive(false); markDone(); return i }
      return i + 1
    })
  }, [tour, markDone])

  const back = useCallback(() => setIndex((i) => Math.max(0, i - 1)), [])

  const current = tour && isActive ? tour.steps[index] ?? null : null

  const value = useMemo<TourContextValue>(() => ({
    tour, index, isActive, current, start, next, back, goTo, finish, skip,
    available: !!tour && tour.steps.length > 0,
  }), [tour, index, isActive, current, start, next, back, goTo, finish, skip])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useTour(): TourContextValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useTour must be used inside a TourProvider')
  return v
}
