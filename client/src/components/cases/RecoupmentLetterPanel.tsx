// End-of-process action: generate a provider recoupment letter PDF assembled
// from this case's rule findings, evidence findings, ERA lines, and the total
// recouped. The letter is saved as a Document on the case and also appears in
// the Intake Portal's Output Files section.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Eye, FileText, Loader2, Receipt } from 'lucide-react'
import {
  generateRecoupmentLetter,
  listCaseLetters,
  type CaseDocument,
} from '../../services/recoupmentService'
import { viewDocument } from '../../services/fileView'
import { evidenceService } from '../../services/evidenceService'
import { formatDate } from '../../utils/dateUtils'

interface Props {
  caseSeq: number
  caseId: string
}

export default function RecoupmentLetterPanel({ caseSeq, caseId }: Props) {
  const qc = useQueryClient()

  const lettersQ = useQuery({
    queryKey: ['case-letters', caseId],
    queryFn: () => listCaseLetters(caseId),
  })
  const genM = useMutation({
    mutationFn: () => generateRecoupmentLetter(caseSeq),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['case-letters', caseId] }),
  })

  const letters = lettersQ.data ?? []

  return (
    <section className="mt-5 border border-gray-200 rounded-xl bg-white">
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <h4 className="text-sm font-semibold text-gray-800 inline-flex items-center gap-2">
          <Receipt className="w-4 h-4 text-gray-400" />
          Recoupment letter
          <span className="text-xs text-gray-400 font-normal">({letters.length})</span>
        </h4>
        <button
          onClick={() => genM.mutate()}
          disabled={genM.isPending}
          className="text-xs px-3 py-1.5 rounded-md bg-[#FE017D] text-white hover:opacity-90 inline-flex items-center gap-1.5 disabled:opacity-50"
        >
          {genM.isPending ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Generating…
            </>
          ) : (
            <>
              <FileText className="w-3.5 h-3.5" /> Generate recoupment letter
            </>
          )}
        </button>
      </div>

      {genM.isError && (
        <p className="px-4 py-2.5 text-sm text-red-700 bg-red-50 border-b border-red-100">
          Could not generate the letter. Please try again.
        </p>
      )}

      <p className="px-4 pt-2.5 text-xs text-gray-400">
        Includes every rule finding, evidence issue, the ERA remittance lines, and
        the total recouped. Saved to the case and the Intake Portal output files.
      </p>

      {letters.length === 0 ? (
        <p className="px-4 py-6 text-sm text-gray-400">No letter generated yet.</p>
      ) : (
        <ul className="divide-y divide-gray-100 mt-1">
          {letters.map((d: CaseDocument) => (
            <li key={d.id} className="flex items-center gap-3 px-4 py-3 text-sm">
              <FileText className="w-4 h-4 text-gray-400 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-gray-900 truncate font-mono text-xs">{d.filename}</div>
                <div className="text-xs text-gray-500">
                  {d.file_size_kb} KB · generated {formatDate(d.uploaded_at)}
                </div>
              </div>
              <button
                onClick={() => viewDocument(d.id).catch(() => alert('Could not open this file.'))}
                className="text-gray-500 hover:text-gray-700 p-1.5 rounded hover:bg-gray-100"
                aria-label={`View ${d.filename}`}
                title="View"
              >
                <Eye className="w-4 h-4" />
              </button>
              <a
                href={evidenceService.downloadUrl(d.id)}
                className="text-gray-500 hover:text-gray-700 p-1.5 rounded hover:bg-gray-100"
                aria-label={`Download ${d.filename}`}
                title="Download"
              >
                <Download className="w-4 h-4" />
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
