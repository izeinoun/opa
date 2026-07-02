import { useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { X, Loader2, CheckCircle2, AlertTriangle, ScanSearch } from 'lucide-react'
import api from '../../services/api'

interface JobStatus {
  job_id: string
  status: 'running' | 'done' | 'error'
  total: number | null
  completed: number
  current: string | null
  findings_created: number | null
  error: string | null
}

interface Props {
  caseId: number
  jobId: string
  onClose: () => void
}

/**
 * Polls a background detector re-run and shows live progress. The run happens
 * server-side regardless of whether this modal is open — closing it just stops
 * watching. On completion we invalidate the case query so findings repopulate
 * automatically.
 */
export default function RerunProgressModal({ caseId, jobId, onClose }: Props) {
  const qc = useQueryClient()
  const refreshedRef = useRef(false)

  const { data } = useQuery<JobStatus>({
    queryKey: ['rerun-status', caseId, jobId],
    queryFn: async () =>
      (await api.get(`/cases/${caseId}/rerun-detectors/status/${jobId}`)).data,
    // Poll while running; stop once the server reports a terminal state.
    refetchInterval: (q) => (q.state.data?.status === 'running' ? 800 : false),
    refetchOnWindowFocus: false,
  })

  const status = data?.status ?? 'running'
  const total = data?.total ?? null
  const completed = data?.completed ?? 0
  const pct = total && total > 0 ? Math.round((completed / total) * 100) : null

  // As soon as the run finishes, refresh the case so new findings show even if
  // the user leaves the modal open.
  useEffect(() => {
    if (status === 'done' && !refreshedRef.current) {
      refreshedRef.current = true
      qc.invalidateQueries({ queryKey: ['case', caseId] })
    }
  }, [status, caseId, qc])

  return (
    <Backdrop onClose={onClose}>
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2.5">
            <div className={`w-9 h-9 rounded-full flex items-center justify-center ${
              status === 'done' ? 'bg-emerald-100'
              : status === 'error' ? 'bg-red-100'
              : 'bg-indigo-100'
            }`}>
              {status === 'done'
                ? <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                : status === 'error'
                  ? <AlertTriangle className="w-5 h-5 text-red-600" />
                  : <ScanSearch className="w-5 h-5 text-indigo-600" />}
            </div>
            <h3 className="text-base font-bold text-gray-900">
              {status === 'done' ? 'Re-run complete'
                : status === 'error' ? 'Re-run failed'
                : 'Re-running rules'}
            </h3>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Progress bar */}
        {status !== 'error' && (
          <div className="mb-3">
            <div className="h-2 w-full rounded-full bg-gray-100 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  status === 'done' ? 'bg-emerald-500' : 'bg-indigo-500'
                } ${pct === null ? 'animate-pulse w-1/3' : ''}`}
                style={pct === null ? undefined : { width: `${status === 'done' ? 100 : pct}%` }}
              />
            </div>
            <div className="flex items-center justify-between mt-2 text-xs text-gray-500">
              <span className="inline-flex items-center gap-1.5">
                {status === 'running' && <Loader2 className="w-3 h-3 animate-spin" />}
                {status === 'done'
                  ? `${data?.findings_created ?? 0} finding${data?.findings_created === 1 ? '' : 's'} recorded`
                  : data?.current
                    ? `Running ${data.current}…`
                    : 'Starting…'}
              </span>
              {total ? <span className="font-mono">{Math.min(completed, total)} / {total}</span> : null}
            </div>
          </div>
        )}

        {/* Body copy */}
        {status === 'running' && (
          <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-3 text-xs text-indigo-800 leading-relaxed">
            This runs in the background — you can <span className="font-semibold">close this window</span> and
            keep working. The rule outcomes and detector findings will populate automatically when it finishes.
          </div>
        )}
        {status === 'done' && (
          <p className="text-sm text-gray-600 leading-relaxed">
            The detector findings and rule outcomes on this case have been refreshed.
          </p>
        )}
        {status === 'error' && (
          <div className="bg-red-50 border border-red-100 rounded-lg p-3 text-xs text-red-700 leading-relaxed">
            {data?.error || 'The re-run could not be completed. Please try again.'}
          </div>
        )}

        {/* Footer */}
        <div className="flex gap-2 mt-5">
          {status === 'running' ? (
            <button
              onClick={onClose}
              className="w-full px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Close — keep running in background
            </button>
          ) : (
            <button
              onClick={onClose}
              className={`w-full px-4 py-2 text-sm font-semibold text-white rounded-lg transition-colors ${
                status === 'error'
                  ? 'bg-gray-700 hover:bg-gray-800'
                  : 'bg-indigo-600 hover:bg-indigo-700'
              }`}
            >
              {status === 'error' ? 'Dismiss' : 'View results'}
            </button>
          )}
        </div>
      </div>
    </Backdrop>
  )
}

function Backdrop({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40"
      onClick={onClose}
    >
      <div onClick={(e) => e.stopPropagation()} className="contents">
        {children}
      </div>
    </div>
  )
}
