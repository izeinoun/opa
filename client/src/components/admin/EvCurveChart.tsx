import { useEffect, useRef, useState } from 'react'

interface CurvePoint { n: number; capture_ratio: number }

interface Props {
  points: CurvePoint[]     // includes (0,0); cumulative capture ratio vs # cases
  maxN: number             // total gate survivors (x domomain end)
  cutN: number             // current cut (within_capacity_count)
  captureRatio: number     // capture ratio at the cut (0–1)
}

const BRAND = '#FE017D'
const PAD = { t: 12, r: 16, b: 26, l: 40 }
const HEIGHT = 200

// Cumulative-EV curve: how much of the recoverable expected value the top-N cases
// capture. Single series, so one hue (the panel brand) — no legend needed; the
// heading names it. Axes recessive, the current cut marked, hover reads a point.
export default function EvCurveChart({ points, maxN, cutN, captureRatio }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(640)
  const [hoverX, setHoverX] = useState<number | null>(null)

  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver((entries) => setW(entries[0].contentRect.width))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])

  if (!points.length || maxN <= 0) return null

  const innerW = Math.max(1, w - PAD.l - PAD.r)
  const innerH = HEIGHT - PAD.t - PAD.b
  const x = (n: number) => PAD.l + (n / maxN) * innerW
  const y = (r: number) => PAD.t + (1 - r) * innerH

  const linePath = points.map((p, i) => `${i ? 'L' : 'M'}${x(p.n).toFixed(1)},${y(p.capture_ratio).toFixed(1)}`).join(' ')
  const areaPath = `${linePath} L${x(points[points.length - 1].n).toFixed(1)},${y(0).toFixed(1)} L${x(0).toFixed(1)},${y(0).toFixed(1)} Z`

  // Nearest curve point to the hovered pixel x (snap for a stable readout).
  let hover: CurvePoint | null = null
  if (hoverX != null) {
    let best = Infinity
    for (const p of points) {
      const d = Math.abs(x(p.n) - hoverX)
      if (d < best) { best = d; hover = p }
    }
  }

  const yTicks = [0, 0.25, 0.5, 0.75, 1]

  return (
    <div ref={ref} className="w-full relative select-none">
      <svg width={w} height={HEIGHT} className="block">
        {/* horizontal gridlines + y labels */}
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={w - PAD.r} y1={y(t)} y2={y(t)} stroke="#f1f1f4" strokeWidth={1} />
            <text x={PAD.l - 6} y={y(t) + 3} textAnchor="end" fontSize={10} fill="#9ca3af">{Math.round(t * 100)}%</text>
          </g>
        ))}
        {/* x labels */}
        <text x={PAD.l} y={HEIGHT - 8} textAnchor="start" fontSize={10} fill="#9ca3af">0</text>
        <text x={w - PAD.r} y={HEIGHT - 8} textAnchor="end" fontSize={10} fill="#9ca3af">{maxN} cases</text>

        {/* area + line */}
        <path d={areaPath} fill={BRAND} fillOpacity={0.09} />
        <path d={linePath} fill="none" stroke={BRAND} strokeWidth={2} vectorEffect="non-scaling-stroke" />

        {/* current cut marker: dashed guides + dot */}
        {cutN > 0 && cutN <= maxN && (
          <g>
            <line x1={x(cutN)} x2={x(cutN)} y1={y(captureRatio)} y2={y(0)} stroke={BRAND} strokeWidth={1} strokeDasharray="3 3" opacity={0.6} />
            <line x1={PAD.l} x2={x(cutN)} y1={y(captureRatio)} y2={y(captureRatio)} stroke={BRAND} strokeWidth={1} strokeDasharray="3 3" opacity={0.6} />
            <circle cx={x(cutN)} cy={y(captureRatio)} r={4} fill={BRAND} />
            <text x={Math.min(x(cutN) + 6, w - PAD.r - 90)} y={y(captureRatio) - 6} fontSize={11} fontWeight={700} fill="#111827">
              {cutN} cases → {(captureRatio * 100).toFixed(1)}%
            </text>
          </g>
        )}

        {/* hover crosshair */}
        {hover && (
          <g>
            <line x1={x(hover.n)} x2={x(hover.n)} y1={PAD.t} y2={y(0)} stroke="#9ca3af" strokeWidth={1} strokeDasharray="2 2" />
            <circle cx={x(hover.n)} cy={y(hover.capture_ratio)} r={3.5} fill="#fff" stroke={BRAND} strokeWidth={2} />
          </g>
        )}

        {/* mouse capture */}
        <rect x={PAD.l} y={PAD.t} width={innerW} height={innerH} fill="transparent"
          onMouseMove={(e) => {
            const rect = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect()
            setHoverX(e.clientX - rect.left)
          }}
          onMouseLeave={() => setHoverX(null)} />
      </svg>

      {hover && (
        <div className="absolute pointer-events-none bg-white border border-gray-200 rounded-md shadow-sm px-2 py-1 text-[11px]"
          style={{ left: Math.min(x(hover.n) + 8, w - 130), top: PAD.t }}>
          <span className="font-semibold text-gray-900">{hover.n} cases</span>
          <span className="text-gray-500"> → </span>
          <span className="font-semibold" style={{ color: BRAND }}>{(hover.capture_ratio * 100).toFixed(1)}%</span>
          <span className="text-gray-500"> of EV</span>
        </div>
      )}
    </div>
  )
}
