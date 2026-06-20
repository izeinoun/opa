// One-line Overview callout: the deterministic rules only see the ERA + claim,
// so any CRITICAL issue the AI evidence review found in the attached chart is
// something the rules structurally couldn't catch. Nudge the analyst toward the
// Evidence tab — but only when we actually have a document to have reviewed.
import { useQuery } from '@tanstack/react-query'
import { FileSearch, ArrowRight } from 'lucide-react'
import { evidenceService, type EvidenceDocument, type EvidenceFinding } from '../../services/evidenceService'

interface Props {
  claimId: string
  onReview: () => void   // switch the case-detail view to the Evidence tab
}

export default function EvidenceIssuesBanner({ claimId, onReview }: Props) {
  // Same query keys as EvidencePanel, so this shares its cache.
  const findingsQ = useQuery({
    queryKey: ['evidence-findings', claimId],
    queryFn:  () => evidenceService.listEvidenceFindings(claimId),
  })
  const docsQ = useQuery({
    queryKey: ['evidence-docs', claimId],
    queryFn:  () => evidenceService.listDocuments(claimId),
  })

  const docs: EvidenceDocument[] = docsQ.data ?? []
  const findings: EvidenceFinding[] = findingsQ.data ?? []

  // Gate: we must actually have a reviewed document (the user's key point —
  // never imply chart issues when we never had the chart).
  const hasChart = docs.some((d) => d.kind === 'medical_record' || d.kind === 'supporting')
  const critical = findings.filter((f) => f.severity === 'critical')
  if (!hasChart || critical.length === 0) return null

  const n = critical.length
  return (
    <button
      onClick={onReview}
      className="w-full flex items-center gap-2.5 px-4 py-2.5 mb-1 rounded-lg border border-red-200 bg-red-50 text-red-800 text-sm hover:bg-red-100 transition-colors text-left"
    >
      <FileSearch className="w-4 h-4 shrink-0" />
      <span className="flex-1">
        Evidence review flagged{' '}
        <strong>{n} critical issue{n === 1 ? '' : 's'}</strong>{' '}
        from the medical record that automated rules couldn't catch.
      </span>
      <span className="inline-flex items-center gap-1 font-medium shrink-0">
        Review <ArrowRight className="w-3.5 h-3.5" />
      </span>
    </button>
  )
}
