import { useQuery } from '@tanstack/react-query'
import { X, FileText } from 'lucide-react'
import api from '../../services/api'

interface SavedNotice {
  notice_id: string
  template_id: string
  lob: string
  status: string
  sent_at?: string | null
  generated_at: string
  letter_content: string
}

interface Props {
  caseSeq: number
  caseNumber: string
  onClose: () => void
}

/**
 * Read-only viewer for the saved provider notice letter. Always available
 * once a case has at least one ProviderNotice — independent of case state.
 */
export default function NoticeLetterViewerModal({ caseSeq, caseNumber, onClose }: Props) {
  const { data, isLoading } = useQuery<SavedNotice[]>({
    queryKey: ['notice-letters', caseSeq],
    queryFn: async () => (await api.get<SavedNotice[]>(`/letters/notices/${caseSeq}`)).data,
  })

  const latest = data?.[0]

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
         onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl flex flex-col overflow-hidden"
           style={{ height: '88vh' }}>
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 flex-shrink-0">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-indigo-600" />
            <div>
              <h2 className="text-lg font-bold text-gray-900">Notice letter</h2>
              <p className="text-xs text-gray-500 font-mono">{caseNumber}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-700">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 bg-gray-50">
          {isLoading ? (
            <div className="space-y-2 animate-pulse">
              {[...Array(8)].map((_, i) => <div key={i} className="h-4 bg-gray-200 rounded" />)}
            </div>
          ) : !latest ? (
            <p className="text-sm text-gray-500 italic text-center py-12">No notice has been generated for this case yet.</p>
          ) : (
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
              <div className="mb-3 pb-3 border-b border-gray-100 flex items-center justify-between text-xs">
                <span className="text-gray-500">
                  Template: <span className="font-mono text-gray-800">{latest.template_id}</span>
                </span>
                <span className="text-gray-500">
                  {latest.sent_at ? `Sent ${latest.sent_at.slice(0, 10)}` : `Generated ${latest.generated_at.slice(0, 10)}`}
                </span>
              </div>
              <div
                className="prose prose-sm max-w-none"
                dangerouslySetInnerHTML={{ __html: latest.letter_content }}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
