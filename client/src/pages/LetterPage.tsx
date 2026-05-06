import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Eye, Send, FileText, CheckCircle } from 'lucide-react'
import { getTemplates, renderLetter, sendNotice, getNotices } from '../services/letterService'
import LetterViewer from '../components/letters/LetterViewer'
import TemplateMetadata from '../components/letters/TemplateMetadata'
import { card } from '../utils/designSystem'
import { formatCurrency } from '../utils/formatUtils'
import { formatDate } from '../utils/dateUtils'
import type { LetterTemplate, RenderedLetter, LOB, RecoveryNotice } from '../types'

const LOB_OPTIONS: (LOB | '')[] = ['', 'MA', 'PPO', 'Medicaid']

const LOB_PILL: Record<string, string> = {
  MA:       'bg-blue-100 text-blue-700',
  PPO:      'bg-purple-100 text-purple-700',
  Medicaid: 'bg-teal-100 text-teal-700',
}

function InputLabel({ children }: { children: React.ReactNode }) {
  return <label className="text-xs font-medium text-gray-500 block mb-1">{children}</label>
}

function ControlInput({ label, ...props }: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div>
      <InputLabel>{label}</InputLabel>
      <input
        {...props}
        className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm
                   focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]
                   transition-colors"
      />
    </div>
  )
}

export default function LetterPage() {
  const [lobFilter,      setLobFilter]      = useState<LOB | ''>('')
  const [selectedTmpl,   setSelectedTmpl]   = useState<LetterTemplate | null>(null)
  const [renderedLetter, setRenderedLetter] = useState<RenderedLetter | null>(null)
  const [caseIdInput,    setCaseIdInput]    = useState('')
  const [amountDemanded, setAmountDemanded] = useState('')
  const [deliveryMethod, setDeliveryMethod] = useState('mail')
  const [responseDue,    setResponseDue]    = useState('')
  const [sendSuccess,    setSendSuccess]    = useState(false)

  const caseId = parseInt(caseIdInput, 10) || 0

  const { data: templates = [], isLoading: loadingTemplates } = useQuery({
    queryKey: ['templates', lobFilter],
    queryFn: () => getTemplates(lobFilter || undefined),
  })

  const { data: notices = [], refetch: refetchNotices } = useQuery<RecoveryNotice[]>({
    queryKey: ['notices', caseId],
    queryFn: () => getNotices(caseId),
    enabled: caseId > 0,
  })

  const renderMutation = useMutation({
    mutationFn: () => renderLetter(caseId, selectedTmpl!.code),
    onSuccess: (data) => setRenderedLetter(data),
  })

  const sendMutation = useMutation({
    mutationFn: () =>
      sendNotice({
        case_id:         caseId,
        template_id:     selectedTmpl!.id,
        amount_demanded: parseFloat(amountDemanded),
        delivery_method: deliveryMethod,
        response_due:    responseDue,
      }),
    onSuccess: () => {
      setSendSuccess(true)
      refetchNotices()
      setTimeout(() => setSendSuccess(false), 3000)
    },
  })

  const filteredTemplates = lobFilter
    ? templates.filter((t) => t.lob === lobFilter)
    : templates

  const canPreview = caseId > 0 && selectedTmpl !== null
  const canSend    = canPreview && !!amountDemanded && !!responseDue

  return (
    <div className="flex flex-col gap-5 h-full">
      <h1 className="text-2xl font-bold text-gray-900">Letter Management</h1>

      <div className="flex gap-5 flex-1 min-h-0">
        {/* Left panel — template list */}
        <div className="w-64 flex-shrink-0 flex flex-col gap-3">
          <div>
            <InputLabel>Filter by LOB</InputLabel>
            <select
              value={lobFilter}
              onChange={(e) => setLobFilter(e.target.value as LOB | '')}
              className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm
                         focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30
                         transition-colors"
            >
              {LOB_OPTIONS.map((o) => (
                <option key={o} value={o}>{o || 'All LOBs'}</option>
              ))}
            </select>
          </div>

          <div className="flex-1 overflow-y-auto space-y-2">
            {loadingTemplates ? (
              [...Array(3)].map((_, i) => (
                <div key={i} className="h-20 bg-white rounded-xl border border-gray-200 animate-pulse" />
              ))
            ) : filteredTemplates.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-8">No templates found.</p>
            ) : (
              filteredTemplates.map((t) => (
                <div
                  key={t.id}
                  onClick={() => { setSelectedTmpl(t); setRenderedLetter(null) }}
                  className={`cursor-pointer rounded-xl transition-all duration-200 ${
                    selectedTmpl?.id === t.id
                      ? 'ring-2 ring-[#FE017D] shadow-sm'
                      : 'hover:shadow-sm'
                  }`}
                >
                  <TemplateMetadata template={t} />
                </div>
              ))
            )}
          </div>
        </div>

        {/* Center — letter viewer */}
        <div className="flex-1 min-w-0 overflow-y-auto">
          {!renderedLetter && !renderMutation.isPending && (
            <div className="h-full flex items-center justify-center bg-white
                            rounded-xl border border-gray-200 shadow-sm">
              <div className="text-center text-gray-400">
                <FileText className="w-10 h-10 mx-auto mb-3 opacity-40" />
                <p className="text-sm">Select a template and click <strong>Preview</strong> to render a letter.</p>
              </div>
            </div>
          )}
          <LetterViewer letter={renderedLetter} isLoading={renderMutation.isPending} />
        </div>

        {/* Right panel — controls */}
        <div className="w-60 flex-shrink-0 flex flex-col gap-4">
          <div className={`${card} space-y-4`}>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Controls
            </h3>

            <ControlInput label="Case ID" type="number" value={caseIdInput}
              onChange={(e) => setCaseIdInput(e.target.value)} placeholder="e.g. 42" />

            {selectedTmpl && (
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-400 mb-1">Template</p>
                <p className="text-sm font-medium text-gray-900">{selectedTmpl.name}</p>
                <div className="flex items-center gap-1.5 mt-1.5">
                  <span className="font-mono text-xs text-gray-400">{selectedTmpl.code}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded-full ${LOB_PILL[selectedTmpl.lob] ?? 'bg-gray-100 text-gray-600'}`}>
                    {selectedTmpl.lob}
                  </span>
                </div>
              </div>
            )}

            <button
              onClick={() => renderMutation.mutate()}
              disabled={!canPreview || renderMutation.isPending}
              className="w-full inline-flex items-center justify-center gap-2 px-3 py-2
                         bg-[#1e3a5f] text-white text-sm rounded-lg
                         hover:bg-[#2a4f7c] disabled:opacity-40 disabled:cursor-not-allowed
                         transition-colors"
            >
              <Eye className="w-4 h-4" />
              {renderMutation.isPending ? 'Rendering…' : 'Preview Letter'}
            </button>

            <hr className="border-gray-100" />

            <ControlInput label="Amount Demanded ($)" type="number" value={amountDemanded}
              onChange={(e) => setAmountDemanded(e.target.value)} placeholder="0.00" />

            <div>
              <InputLabel>Delivery Method</InputLabel>
              <select value={deliveryMethod} onChange={(e) => setDeliveryMethod(e.target.value)}
                className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm
                           focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 transition-colors">
                {['mail','fax','email','portal'].map((m) => (
                  <option key={m} value={m}>{m.charAt(0).toUpperCase() + m.slice(1)}</option>
                ))}
              </select>
            </div>

            <ControlInput label="Response Due" type="date" value={responseDue}
              onChange={(e) => setResponseDue(e.target.value)} />

            <button
              onClick={() => sendMutation.mutate()}
              disabled={!canSend || sendMutation.isPending}
              className="w-full inline-flex items-center justify-center gap-2 px-3 py-2
                         bg-[#FE017D] text-white text-sm rounded-lg
                         hover:bg-[#e5006f] disabled:opacity-40 disabled:cursor-not-allowed
                         transition-colors"
            >
              <Send className="w-4 h-4" />
              {sendMutation.isPending ? 'Sending…' : 'Send Notice'}
            </button>

            {sendSuccess && (
              <div className="flex items-center gap-1.5 text-xs text-green-700 bg-green-50
                              border border-green-200 rounded-lg px-3 py-2">
                <CheckCircle className="w-3.5 h-3.5" />
                Notice sent successfully!
              </div>
            )}
            {sendMutation.isError && (
              <p className="text-xs text-red-600 text-center">Failed to send notice.</p>
            )}
          </div>

          {/* Sent notices */}
          {caseId > 0 && notices.length > 0 && (
            <div className={card}>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                Sent Notices
              </h3>
              <ul className="space-y-2">
                {notices.map((n) => (
                  <li key={n.id} className="text-xs bg-gray-50 rounded-lg p-2.5">
                    <div className="flex justify-between mb-1">
                      <span className="font-medium text-gray-900">{formatDate(n.sent_date)}</span>
                      <span className={`px-1.5 py-0.5 rounded-full text-xs font-medium ${
                        n.status === 'paid'    ? 'bg-green-100 text-green-700' :
                        n.status === 'overdue' ? 'bg-red-100 text-red-700' :
                        'bg-gray-100 text-gray-600'
                      }`}>{n.status}</span>
                    </div>
                    <p className="text-gray-500">{formatCurrency(n.amount_demanded)} via {n.delivery_method}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
