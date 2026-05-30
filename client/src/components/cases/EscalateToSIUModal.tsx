// Modal: PI analyst escalates a case to the SIU workspace.
// Calls POST /api/siu/escalate. On success the case is frozen (read-only
// outside SIU) and shows up in the SIU queue at :5178.
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { AlertTriangle, ShieldAlert, X } from 'lucide-react'
import api from '../../services/api'

type InvestigationType =
  | 'TIME_VOLUME_ANOMALY'
  | 'SUBROGATION'
  | 'EXCLUDED_PROVIDER'
  | 'FRAUD_PATTERN'
  | 'OTHER'

interface Props {
  caseId: string                  // claim_id UUID (escalate API takes case_id as UUID)
  caseNumber: string              // for display
  onClose: () => void
  onEscalated: () => void
}

const TYPES: Array<[InvestigationType, string, string]> = [
  ['FRAUD_PATTERN',       'Fraud pattern',           'Repeated suspicious billing patterns; likely intentional'],
  ['TIME_VOLUME_ANOMALY', 'Time / volume anomaly',   'Impossible service-time or volume for the provider'],
  ['SUBROGATION',         'Subrogation',             'Third-party liability indicators on the claim'],
  ['EXCLUDED_PROVIDER',   'Excluded provider',       'Provider appears on OIG/SAM exclusion lists'],
  ['OTHER',               'Other',                   'Doesn\'t fit the categories above'],
]

export default function EscalateToSIUModal({
  caseId, caseNumber, onClose, onEscalated,
}: Props) {
  const [type, setType] = useState<InvestigationType>('FRAUD_PATTERN')
  const [reason, setReason] = useState('')

  const mut = useMutation({
    mutationFn: async () => {
      const { data } = await api.post('/siu/escalate', {
        case_id: caseId,
        investigation_type: type,
        escalation_source: 'analyst_referral',
        escalation_reason: reason,
      })
      return data
    },
    onSuccess: onEscalated,
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl w-full max-w-lg shadow-xl">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-5 h-5 text-amber-600" />
            <h3 className="text-base font-semibold">Escalate to SIU</h3>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-5 space-y-4">
          <div className="text-xs text-gray-500 font-mono">{caseNumber}</div>

          <div className="p-3 bg-amber-50 border border-amber-200 rounded-md flex items-start gap-2 text-sm">
            <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
            <div className="text-amber-900">
              Escalating freezes the case's evidence bundle. PI analysts and
              supervisors will no longer be able to modify the case until SIU
              closes the investigation.
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">
              Investigation type
            </label>
            <div className="space-y-1.5">
              {TYPES.map(([key, label, desc]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setType(key)}
                  className={`w-full text-left px-3 py-2 rounded-md border text-sm transition ${
                    type === key
                      ? 'border-amber-500 bg-amber-50/40 ring-1 ring-amber-300'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="font-medium text-gray-900">{label}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{desc}</div>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">
              Reason for escalation
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={4}
              placeholder="Briefly describe why this case requires SIU attention…"
              className="w-full px-3 py-2 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-amber-300"
            />
          </div>

          {mut.isError && (
            <p className="text-xs text-red-600">
              Failed: {(mut.error as Error)?.message ?? 'unknown error'}
            </p>
          )}
        </div>
        <div className="px-5 py-3.5 border-t border-gray-200 flex justify-end gap-2">
          <button
            onClick={onClose}
            disabled={mut.isPending}
            className="px-3.5 py-2 rounded-md text-sm text-gray-600 hover:bg-gray-100"
          >
            Cancel
          </button>
          <button
            onClick={() => mut.mutate()}
            disabled={mut.isPending || !reason.trim()}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-md text-sm font-medium bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50"
          >
            <ShieldAlert className="w-4 h-4" />
            {mut.isPending ? 'Escalating…' : 'Escalate to SIU'}
          </button>
        </div>
      </div>
    </div>
  )
}
