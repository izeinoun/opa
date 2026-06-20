import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Link2, CheckCircle, Inbox, Eye } from 'lucide-react'
import { listUnmatched, resolveIntake, type UnmatchedFile } from '../services/fileIntake'
import { viewIntakeFile } from '../services/fileView'

function fmtMoney(v: number | null): string {
  if (v == null) return '—'
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}

function UnmatchedCard({ doc }: { doc: UnmatchedFile }) {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: (caseId: string) => resolveIntake(doc.intake_id, caseId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['intake-unmatched'] })
      qc.invalidateQueries({ queryKey: ['intake-files'] })
    },
  })

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900 font-mono truncate" title={doc.filename}>
            {doc.filename}
          </p>
          <p className="text-xs text-gray-500 mt-0.5">
            {doc.app === 'payguard' ? 'PayGuard' : 'ClaimGuard'} · {doc.category}
            {doc.message ? ` · ${doc.message}` : ''}
          </p>
          <button
            onClick={() => viewIntakeFile(doc.intake_id).catch(() => alert('Could not open this file.'))}
            className="mt-1.5 inline-flex items-center gap-1 text-xs text-gray-500 hover:text-gray-800"
            title="View file"
          >
            <Eye className="w-3.5 h-3.5" /> View file
          </button>
        </div>
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-700 flex-shrink-0">
          <Inbox className="w-3 h-3" /> Unmatched
        </span>
      </div>

      {/* Extracted identifiers */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 text-xs">
        <div>
          <p className="text-[10px] text-gray-400 uppercase tracking-wider">Member #</p>
          <p className="text-gray-800 font-medium">{doc.extracted_member_number || '—'}</p>
        </div>
        <div>
          <p className="text-[10px] text-gray-400 uppercase tracking-wider">Name</p>
          <p className="text-gray-800 font-medium">{doc.extracted_member_name || '—'}</p>
        </div>
        <div>
          <p className="text-[10px] text-gray-400 uppercase tracking-wider">DOB</p>
          <p className="text-gray-800 font-medium">{doc.extracted_dob || '—'}</p>
        </div>
        <div>
          <p className="text-[10px] text-gray-400 uppercase tracking-wider">Dates of service</p>
          <p className="text-gray-800 font-medium">
            {doc.extracted_service_dates.length ? doc.extracted_service_dates.join(', ') : '—'}
          </p>
        </div>
      </div>

      {/* Per-line (CPT + DoS) pairs — the basis for line-to-line matching */}
      {doc.extracted_service_lines.some((l) => l.cpt && l.date) && (
        <div className="mb-4">
          <p className="text-[10px] text-gray-400 uppercase tracking-wider mb-1.5">
            Procedure lines (CPT · date of service)
          </p>
          <div className="flex flex-wrap gap-1.5">
            {doc.extracted_service_lines
              .filter((l) => l.cpt && l.date)
              .map((l, i) => (
                <span
                  key={`${l.cpt}-${l.date}-${i}`}
                  className="inline-flex items-center gap-1.5 text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded"
                >
                  <span className="font-mono font-semibold text-gray-900">{l.cpt}</span>
                  <span className="text-gray-400">·</span>
                  <span>{l.date}</span>
                </span>
              ))}
          </div>
        </div>
      )}

      {/* Candidate cases */}
      <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-2">
        Select the matching case
      </p>
      {doc.candidates.length === 0 ? (
        <p className="text-xs text-gray-400 italic">
          No candidate cases for this member. The matching ERA case may not exist yet.
        </p>
      ) : (
        <div className="space-y-2">
          {doc.candidates.map((c) => (
            <label
              key={c.case_id}
              className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors
                ${selected === c.case_id ? 'border-[#FE017D] bg-pink-50' : 'border-gray-200 hover:bg-gray-50'}`}
            >
              <input
                type="radio"
                name={`case-${doc.intake_id}`}
                value={c.case_id}
                checked={selected === c.case_id}
                onChange={() => setSelected(c.case_id)}
                className="accent-[#FE017D]"
              />
              <div className="flex-1 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                <span className="font-mono font-semibold text-gray-900">{c.case_number}</span>
                <span className="text-gray-600">{c.member_name || '—'}</span>
                <span className="text-gray-600">
                  {c.service_from_date}{c.service_to_date && c.service_to_date !== c.service_from_date ? ` → ${c.service_to_date}` : ''}
                </span>
                <span className="text-gray-600">{c.priority} · {fmtMoney(c.total_overpayment_amount)}</span>
              </div>
              <Link
                to={`/cases/${c.case_id}`}
                onClick={(e) => e.stopPropagation()}
                className="text-[11px] text-gray-400 hover:text-[#FE017D] hover:underline"
              >
                view
              </Link>
            </label>
          ))}
        </div>
      )}

      <div className="flex items-center justify-end gap-3 mt-4">
        {mutation.isError && (
          <span className="text-xs text-red-600">
            {(mutation.error as any)?.response?.data?.detail ?? 'Link failed'}
          </span>
        )}
        <button
          onClick={() => selected && mutation.mutate(selected)}
          disabled={!selected || mutation.isPending}
          className="inline-flex items-center gap-2 px-4 py-2 bg-[#FE017D] text-white text-sm font-semibold
                     rounded-lg hover:bg-[#e5006f] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <Link2 className="w-4 h-4" />
          Link to selected case
        </button>
      </div>
    </div>
  )
}

export default function UnmatchedDocumentsPage() {
  const { data: docs = [], isLoading } = useQuery({
    queryKey: ['intake-unmatched'],
    queryFn: listUnmatched,
  })

  return (
    <div className="flex flex-col gap-5 max-w-4xl">
      <div>
        <Link to="/file-intake" className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 mb-2">
          <ArrowLeft className="w-4 h-4" /> Back to File Intake
        </Link>
        <h1 className="text-2xl font-bold text-gray-900">Unmatched Documents</h1>
        <p className="text-sm text-gray-500 mt-1">
          Documents that matched no case, or more than one, after matching on member and service
          date. Pick the correct case to link each one.
        </p>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : docs.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-10 text-center">
          <CheckCircle className="w-8 h-8 text-green-400 mx-auto mb-2" />
          <p className="text-sm text-gray-500">No unmatched documents. Everything is linked.</p>
        </div>
      ) : (
        docs.map((doc) => <UnmatchedCard key={doc.intake_id} doc={doc} />)
      )}
    </div>
  )
}
