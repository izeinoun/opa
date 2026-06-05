import { ExternalLink, AlertTriangle } from 'lucide-react'
import { formatDate } from '../../../utils/dateUtils'

// ── Confidence gauge ──────────────────────────────────────────────────────────

export function ConfidenceGauge({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = value >= 0.8 ? 'bg-green-500' : value >= 0.6 ? 'bg-amber-400' : 'bg-red-400'
  const text  = value >= 0.8 ? 'text-green-700' : value >= 0.6 ? 'text-amber-700' : 'text-red-700'
  const bg    = value >= 0.8 ? 'bg-green-50'   : value >= 0.6 ? 'bg-amber-50'   : 'bg-red-50'
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold ${bg} ${text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${color}`} />
      {pct}%
    </span>
  )
}

// ── Rule certainty badge ──────────────────────────────────────────────────────

const CERTAINTY: Record<string, string> = {
  mandatory: 'bg-[#1e3a5f]/10 text-[#1e3a5f] border border-[#1e3a5f]/20',
  guideline:  'bg-blue-50 text-blue-700 border border-blue-200',
  heuristic:  'bg-gray-100 text-gray-600 border border-gray-200',
}

export function CertaintyBadge({ value }: { value: string }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold capitalize ${CERTAINTY[value] ?? CERTAINTY.heuristic}`}>
      {value}
    </span>
  )
}

// ── Coverage type badge ───────────────────────────────────────────────────────

const COVERAGE: Record<string, string> = {
  required:   'bg-green-100 text-green-800 border border-green-200',
  supporting: 'bg-blue-100 text-blue-800 border border-blue-200',
  excluded:   'bg-red-100 text-red-800 border border-red-200',
}

export function CoverageTypeBadge({ value }: { value: string }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold capitalize ${COVERAGE[value] ?? 'bg-gray-100 text-gray-600'}`}>
      {value}
    </span>
  )
}

// ── Provenance block ──────────────────────────────────────────────────────────

interface ProvenanceProps {
  authority: string | null
  document: string | null
  url?: string | null
  reviewedAt: string | null
}

export function ProvenanceBlock({ authority, document, url, reviewedAt }: ProvenanceProps) {
  const isStale = reviewedAt
    ? new Date(reviewedAt) < new Date(Date.now() - 365 * 24 * 60 * 60 * 1000)
    : true

  return (
    <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 text-xs space-y-1.5">
      <p className="font-semibold text-gray-500 uppercase tracking-wider text-[10px]">Source</p>
      {authority && <p className="text-gray-700"><span className="text-gray-400">Authority:</span> {authority}</p>}
      {document && (
        <div className="flex items-start gap-1">
          <span className="text-gray-400 shrink-0">Document:</span>
          {url
            ? <a href={url} target="_blank" rel="noopener noreferrer"
                className="text-[#FE017D] hover:underline inline-flex items-center gap-0.5">
                {document} <ExternalLink className="w-2.5 h-2.5" />
              </a>
            : <span className="text-gray-700">{document}</span>}
        </div>
      )}
      <div className="flex items-center gap-1.5">
        <span className="text-gray-400">Last reviewed:</span>
        <span className={isStale ? 'text-amber-700 font-medium' : 'text-gray-700'}>
          {reviewedAt ? formatDate(reviewedAt) : '—'}
        </span>
        {isStale && <span title="Not reviewed in 12+ months"><AlertTriangle className="w-3 h-3 text-amber-500" /></span>}
      </div>
    </div>
  )
}

// ── Inline editable text area ─────────────────────────────────────────────────

interface EditableTextProps {
  label: string
  value: string | null
  placeholder?: string
  onSave: (val: string | null) => void
  saving?: boolean
  rows?: number
}

export function EditableText({ label, value, placeholder, onSave, saving, rows = 4 }: EditableTextProps) {
  return (
    <div className="space-y-1">
      <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider">{label}</label>
      <textarea
        rows={rows}
        defaultValue={value ?? ''}
        placeholder={placeholder}
        disabled={saving}
        onBlur={e => {
          const next = e.target.value.trim() || null
          if (next !== value) onSave(next)
        }}
        className="w-full text-sm text-gray-800 bg-white border border-gray-200 rounded-lg px-3 py-2
                   focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]
                   resize-none placeholder-gray-300 disabled:opacity-60"
      />
    </div>
  )
}

// ── Master-detail shell ───────────────────────────────────────────────────────

interface MasterDetailProps {
  search: string
  onSearch: (v: string) => void
  searchPlaceholder?: string
  listHeader?: React.ReactNode
  listItems: React.ReactNode
  detail: React.ReactNode
  emptyMessage?: string
  hasSelection: boolean
}

export function MasterDetail({
  search, onSearch, searchPlaceholder, listHeader, listItems, detail, hasSelection,
}: MasterDetailProps) {
  return (
    <div className="flex h-full min-h-0">
      {/* Left list */}
      <div className="w-72 flex-shrink-0 border-r border-gray-200 flex flex-col bg-white">
        <div className="p-3 border-b border-gray-100 space-y-2">
          <input
            value={search}
            onChange={e => onSearch(e.target.value)}
            placeholder={searchPlaceholder ?? 'Search…'}
            className="w-full px-3 py-1.5 text-sm bg-gray-50 border border-gray-200 rounded-lg
                       focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]"
          />
          {listHeader}
        </div>
        <div className="flex-1 overflow-y-auto divide-y divide-gray-50">
          {listItems}
        </div>
      </div>

      {/* Right detail */}
      <div className="flex-1 overflow-y-auto bg-gray-50">
        {hasSelection
          ? <div className="p-5">{detail}</div>
          : <div className="h-full flex items-center justify-center text-sm text-gray-400">
              Select an item to view details
            </div>
        }
      </div>
    </div>
  )
}
