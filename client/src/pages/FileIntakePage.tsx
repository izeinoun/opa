import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  FileText, FileStack, Stethoscope, FileSpreadsheet, UploadCloud,
  CheckCircle, Link2, AlertTriangle, XCircle, Trash2, Inbox, Eye,
} from 'lucide-react'
import {
  uploadIntake, listIntake, deleteIntake,
  type IntakeApp, type IntakeCategory, type IntakeFile, type IntakeStatus,
} from '../services/fileIntake'
import { viewIntakeFile, viewOutputFile } from '../services/fileView'
import { listOutputFiles, type OutputFile } from '../services/recoupmentService'

const PAYGUARD = '#FE017D'

type FolderSpec = {
  app: IntakeApp
  category: IntakeCategory
  label: string
  hint: string
  accept: string
  icon: any
}

const FOLDERS: { title: string; accent: string; folders: FolderSpec[] }[] = [
  {
    title: 'PayGuard — Post-pay',
    accent: PAYGUARD,
    folders: [
      { app: 'payguard', category: '835', label: '835s', hint: 'X12 ERA → creates a case', accept: '.x12,.835,.edi,.txt', icon: FileSpreadsheet },
      { app: 'payguard', category: '837', label: '837s', hint: 'X12 claim → links to a case', accept: '.x12,.837,.edi,.txt', icon: FileStack },
      { app: 'payguard', category: 'medical', label: 'Medical Documents', hint: 'Clinical PDF → links to a case', accept: '.pdf', icon: Stethoscope },
    ],
  },
  {
    title: 'ClaimGuard — Pre-pay',
    accent: '#2563eb',
    folders: [
      { app: 'claimguard', category: 'claim_pdf', label: 'Claim PDFs', hint: 'CMS-1500 / UB-04 → creates a pre-pay claim', accept: '.pdf', icon: FileText },
    ],
  },
]

const STATUS_STYLE: Record<IntakeStatus, { label: string; cls: string; icon: any }> = {
  pending:      { label: 'Processing…', cls: 'bg-gray-100 text-gray-600',    icon: UploadCloud },
  case_created: { label: 'Case created', cls: 'bg-green-100 text-green-700',  icon: CheckCircle },
  linked:       { label: 'Linked',       cls: 'bg-blue-100 text-blue-700',    icon: Link2 },
  unmatched:    { label: 'Unmatched',    cls: 'bg-amber-100 text-amber-700',  icon: AlertTriangle },
  rejected:     { label: 'Rejected',     cls: 'bg-red-100 text-red-700',      icon: XCircle },
  error:        { label: 'Error',        cls: 'bg-red-100 text-red-700',      icon: XCircle },
}

function StatusBadge({ status }: { status: IntakeStatus }) {
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.pending
  const Icon = s.icon
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${s.cls}`}>
      <Icon className="w-3 h-3" />
      {s.label}
    </span>
  )
}

function FolderCard({ spec, onUploaded }: { spec: FolderSpec; onUploaded: (f: IntakeFile) => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const Icon = spec.icon

  const mutation = useMutation({
    mutationFn: (file: File) => uploadIntake(file, spec.app, spec.category),
    onSuccess: onUploaded,
  })

  function handleFiles(files: FileList | null) {
    if (files && files.length) mutation.mutate(files[0])
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files) }}
      onClick={() => inputRef.current?.click()}
      className={`cursor-pointer rounded-xl border-2 border-dashed p-5 transition-colors
        ${dragOver ? 'border-[#FE017D] bg-pink-50' : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50'}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={spec.accept}
        className="hidden"
        onChange={(e) => { handleFiles(e.target.files); e.target.value = '' }}
      />
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0">
          <Icon className="w-5 h-5 text-gray-500" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900">{spec.label}</p>
          <p className="text-xs text-gray-500 mt-0.5">{spec.hint}</p>
          <p className="text-[11px] text-gray-400 mt-2 inline-flex items-center gap-1">
            <UploadCloud className="w-3 h-3" />
            {mutation.isPending ? 'Uploading & processing…' : 'Drop a file or click to upload'}
          </p>
          {mutation.isError && (
            <p className="text-[11px] text-red-600 mt-1">
              {(mutation.error as any)?.response?.data?.detail ?? 'Upload failed'}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

export default function FileIntakePage() {
  const qc = useQueryClient()
  const { data: recent = [] } = useQuery({ queryKey: ['intake-files'], queryFn: () => listIntake() })
  // Outputs (recoupment letters) generated from the cases these intakes fed —
  // shown inline as the "response" to each intake.
  const { data: outputs = [] } = useQuery({ queryKey: ['intake-outputs'], queryFn: () => listOutputFiles() })
  const outputsByCase = new Map<string, OutputFile[]>()
  for (const o of outputs) {
    if (!o.case_id) continue
    const arr = outputsByCase.get(o.case_id) ?? []
    arr.push(o)
    outputsByCase.set(o.case_id, arr)
  }

  const unmatchedCount = recent.filter((r) => r.status === 'unmatched').length

  const delMutation = useMutation({
    mutationFn: (id: string) => deleteIntake(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['intake-files'] }),
  })

  function refresh() {
    qc.invalidateQueries({ queryKey: ['intake-files'] })
    qc.invalidateQueries({ queryKey: ['intake-unmatched'] })
  }

  return (
    <div className="flex flex-col gap-6 max-w-5xl">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">File Intake</h1>
          <p className="text-sm text-gray-500 mt-1">
            Simulated drop-folder ingestion. Drop a file into a folder and it is processed
            immediately — 835s open a case; 837s and medical documents are matched to an
            existing case by member and service date.
          </p>
        </div>
        <Link
          to="/file-intake/unmatched"
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-amber-200 bg-amber-50
                     text-amber-700 text-sm font-semibold hover:bg-amber-100 transition-colors flex-shrink-0"
        >
          <Inbox className="w-4 h-4" />
          Unmatched
          {unmatchedCount > 0 && (
            <span className="min-w-[20px] h-5 px-1.5 bg-amber-500 text-white text-xs font-bold rounded-full flex items-center justify-center">
              {unmatchedCount}
            </span>
          )}
        </Link>
      </div>

      {/* Folders */}
      {FOLDERS.map((group) => (
        <div key={group.title} className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <div className="flex items-center gap-2 mb-4">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: group.accent }} />
            <h2 className="text-sm font-bold text-gray-900">{group.title}</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {group.folders.map((spec) => (
              <FolderCard key={spec.category} spec={spec} onUploaded={refresh} />
            ))}
          </div>
        </div>
      ))}

      {/* Recent activity */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="px-5 py-3 border-b border-gray-100">
          <h2 className="text-sm font-bold text-gray-900">Recent uploads</h2>
        </div>
        {recent.length === 0 ? (
          <p className="px-5 py-8 text-sm text-gray-400 text-center">No files uploaded yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] font-semibold text-gray-400 uppercase tracking-wider">
                <th className="px-5 py-2">File</th>
                <th className="px-3 py-2">Folder</th>
                <th className="px-3 py-2">Member</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Result</th>
                <th className="px-3 py-2">Output</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {recent.map((r) => (
                <tr key={r.intake_id} className="border-t border-gray-50 hover:bg-gray-50">
                  <td className="px-5 py-2.5 font-mono text-xs text-gray-700 max-w-[220px] truncate" title={r.filename}>
                    {r.filename}
                  </td>
                  <td className="px-3 py-2.5 text-gray-600">{r.app === 'payguard' ? 'PG' : 'CG'} · {r.category}</td>
                  <td className="px-3 py-2.5 text-gray-600">
                    {r.extracted_member_name || r.extracted_member_number || '—'}
                  </td>
                  <td className="px-3 py-2.5"><StatusBadge status={r.status} /></td>
                  <td className="px-3 py-2.5">
                    {r.result_case_sequence != null ? (
                      <Link to={`/cases/${r.result_case_sequence}`} className="text-[#FE017D] hover:underline font-medium">
                        {r.result_case_number ?? 'View case'}
                      </Link>
                    ) : r.status === 'unmatched' ? (
                      <Link to="/file-intake/unmatched" className="text-amber-600 hover:underline font-medium">
                        Resolve →
                      </Link>
                    ) : (
                      <span className="text-gray-400 text-xs" title={r.message ?? ''}>
                        {r.message ? (r.message.length > 40 ? r.message.slice(0, 40) + '…' : r.message) : '—'}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    {(() => {
                      const outs = r.result_case_id ? outputsByCase.get(r.result_case_id) : undefined
                      if (!outs || outs.length === 0) return <span className="text-gray-300">—</span>
                      return (
                        <button
                          onClick={() => viewOutputFile(outs[0].document_id).catch(() => alert('Could not open this file.'))}
                          className="inline-flex items-center gap-1 text-xs text-[#FE017D] hover:underline font-medium"
                          title={outs[0].filename}
                        >
                          <FileText className="w-3.5 h-3.5" />
                          Letter{outs.length > 1 ? ` (${outs.length})` : ''}
                        </button>
                      )
                    })()}
                  </td>
                  <td className="px-3 py-2.5 text-right whitespace-nowrap">
                    <button
                      onClick={() => viewIntakeFile(r.intake_id).catch(() => alert('Could not open this file.'))}
                      className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-gray-700 transition-colors"
                      title="View file"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => delMutation.mutate(r.intake_id)}
                      className="p-1 rounded hover:bg-gray-200 text-gray-400 hover:text-red-500 transition-colors ml-1"
                      title="Delete intake record"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
