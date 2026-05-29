// Evidence tab on the case-detail page:
//   • upload supporting clinical PDFs (medical_record by default)
//   • see the list of documents already attached
//   • see the AI evidence-validation findings (auto-triggered on upload of
//     a medical_record PDF; can be re-run on demand)
import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileText, Loader2, Trash2, UploadCloud, RotateCcw } from 'lucide-react'
import {
  evidenceService,
  type EvidenceDocument,
  type EvidenceFinding,
} from '../../services/evidenceService'
import { formatDate } from '../../utils/dateUtils'

interface Props {
  claimId: string
  userId: string | null
}

const SEVERITY_STYLES: Record<string, string> = {
  critical: 'bg-red-50 text-red-700 ring-1 ring-red-200',
  warning:  'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
  ok:       'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
}

const KIND_LABEL: Record<string, string> = {
  claim_form:     'Claim form',
  supporting:     'Supporting',
  medical_record: 'Medical record',
}

export default function EvidencePanel({ claimId, userId }: Props) {
  const qc = useQueryClient()
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [dragOver, setDragOver] = useState(false)

  const docsQ = useQuery({
    queryKey: ['evidence-docs', claimId],
    queryFn:  () => evidenceService.listDocuments(claimId),
  })
  const findingsQ = useQuery({
    queryKey: ['evidence-findings', claimId],
    queryFn:  () => evidenceService.listEvidenceFindings(claimId),
    // Poll briefly after an upload so the auto-triggered AI findings appear.
    refetchInterval: (data) => (Array.isArray(data) && data.length > 0 ? false : 5_000),
  })

  const uploadM = useMutation({
    mutationFn: (file: File) =>
      evidenceService.uploadDocument(claimId, file, 'medical_record', userId ?? undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['evidence-docs', claimId] })
      qc.invalidateQueries({ queryKey: ['evidence-findings', claimId] })
    },
  })
  const deleteM = useMutation({
    mutationFn: (docId: string) => evidenceService.deleteDocument(docId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['evidence-docs', claimId] }),
  })
  const runValidationM = useMutation({
    mutationFn: () => evidenceService.runValidateEvidence(claimId),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ['evidence-findings', claimId] }),
  })

  const handleFile = (file: File) => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      alert('Only PDF files are accepted.')
      return
    }
    uploadM.mutate(file)
  }

  const docs = docsQ.data ?? []
  const findings = findingsQ.data ?? []

  return (
    <div className="space-y-5">
      {/* ── Upload ──────────────────────────────────────────────────────── */}
      <section className="border border-gray-200 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-semibold text-gray-800">
            Attach supporting documentation
          </h4>
          <span className="text-xs text-gray-400">
            PDF only — text is auto-extracted on upload
          </span>
        </div>
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragOver(false)
            const f = e.dataTransfer.files[0]
            if (f) handleFile(f)
          }}
          className={`border-2 border-dashed rounded-lg px-6 py-5 text-center transition ${
            dragOver
              ? 'border-[#FE017D] bg-pink-50/40'
              : 'border-gray-200 bg-gray-50'
          }`}
        >
          <UploadCloud className="w-7 h-7 mx-auto text-gray-400 mb-2" />
          <p className="text-sm text-gray-600">
            Drag a PDF here, or{' '}
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="text-[#FE017D] hover:underline font-medium"
            >
              browse
            </button>
          </p>
          <p className="text-xs text-gray-400 mt-1">
            Uploads as <code>kind=medical_record</code>; AI evidence validation
            runs automatically once text is extracted.
          </p>
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) handleFile(f)
              e.target.value = ''
            }}
          />
          {uploadM.isPending && (
            <div className="mt-3 flex items-center justify-center gap-2 text-xs text-gray-500">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Uploading + extracting text…
            </div>
          )}
        </div>
        {uploadM.isError && (
          <p className="mt-2 text-xs text-red-600">
            Upload failed: {(uploadM.error as Error)?.message ?? 'unknown error'}
          </p>
        )}
      </section>

      {/* ── Document list ────────────────────────────────────────────────── */}
      <section className="border border-gray-200 rounded-xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <h4 className="text-sm font-semibold text-gray-800">
            Documents
            <span className="text-xs text-gray-400 font-normal ml-2">
              ({docs.length})
            </span>
          </h4>
        </div>
        {docsQ.isLoading ? (
          <p className="px-4 py-6 text-center text-sm text-gray-400">Loading…</p>
        ) : docs.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-gray-400">
            No documents attached yet.
          </p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {docs.map((d: EvidenceDocument) => (
              <li key={d.id} className="flex items-center gap-3 px-4 py-3 text-sm">
                <FileText className="w-4 h-4 text-gray-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="text-gray-900 truncate">{d.filename}</div>
                  <div className="text-xs text-gray-500 flex gap-2 items-center">
                    <span className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 text-[11px]">
                      {KIND_LABEL[d.kind] ?? d.kind}
                    </span>
                    <span>{d.file_size_kb} KB</span>
                    <span>·</span>
                    <span>uploaded {formatDate(d.uploaded_at)}</span>
                  </div>
                </div>
                <a
                  href={evidenceService.downloadUrl(d.id)}
                  className="text-gray-500 hover:text-gray-700 p-1.5 rounded hover:bg-gray-100"
                  aria-label={`Download ${d.filename}`}
                >
                  <Download className="w-4 h-4" />
                </a>
                <button
                  onClick={() => {
                    if (confirm(`Delete ${d.filename}?`)) deleteM.mutate(d.id)
                  }}
                  className="text-gray-500 hover:text-red-600 p-1.5 rounded hover:bg-gray-100"
                  aria-label={`Delete ${d.filename}`}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── AI evidence findings ────────────────────────────────────────── */}
      <section className="border border-gray-200 rounded-xl">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
          <h4 className="text-sm font-semibold text-gray-800">
            AI evidence validation
            <span className="text-xs text-gray-400 font-normal ml-2">
              ({findings.length} finding{findings.length === 1 ? '' : 's'})
            </span>
          </h4>
          <button
            onClick={() => runValidationM.mutate()}
            disabled={runValidationM.isPending}
            className="text-xs px-3 py-1.5 rounded-md border border-gray-200 hover:bg-gray-50 text-gray-700 inline-flex items-center gap-1.5 disabled:opacity-50"
          >
            {runValidationM.isPending ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Running…
              </>
            ) : (
              <>
                <RotateCcw className="w-3.5 h-3.5" /> Re-run validation
              </>
            )}
          </button>
        </div>
        {findingsQ.isLoading ? (
          <p className="px-4 py-6 text-center text-sm text-gray-400">Loading…</p>
        ) : findings.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-gray-400">
            {docs.length === 0
              ? 'Attach a medical-record PDF to trigger AI evidence validation.'
              : 'Validation pending or no findings yet. Try Re-run.'}
          </p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {findings.map((f: EvidenceFinding) => (
              <li key={f.id} className="px-4 py-3.5 text-sm">
                <div className="flex items-start gap-3">
                  <span
                    className={`text-[11px] px-2 py-0.5 rounded-full font-medium uppercase tracking-wide ${
                      SEVERITY_STYLES[f.severity] ?? SEVERITY_STYLES.warning
                    }`}
                  >
                    {f.severity}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <span className="font-medium text-gray-900">
                        {f.title ?? 'Evidence finding'}
                      </span>
                      {f.code && (
                        <span className="text-xs text-gray-500 font-mono">
                          {f.code}
                        </span>
                      )}
                    </div>
                    <p className="text-gray-600 mt-1 whitespace-pre-line">
                      {f.body}
                    </p>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
        {runValidationM.isError && (
          <p className="px-4 py-2 text-xs text-red-600 border-t border-gray-100">
            Validation failed: {(runValidationM.error as Error)?.message ?? 'unknown error'}
          </p>
        )}
      </section>
    </div>
  )
}
