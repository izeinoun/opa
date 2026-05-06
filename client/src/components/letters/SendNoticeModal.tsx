import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Eye, Send, CheckCircle } from 'lucide-react'
import { getTemplates, renderLetter, sendNotice } from '../../services/letterService'
import LetterViewer from './LetterViewer'
import TemplateMetadata from './TemplateMetadata'
import type { LetterTemplate, RenderedLetter } from '../../types'

interface Props {
  caseId: number
  caseNumber: string
  lob: string
  amountAtRisk: number
  onClose: () => void
}

const LOB_PILL: Record<string, string> = {
  MA:       'bg-blue-100 text-blue-700',
  PPO:      'bg-purple-100 text-purple-700',
  Medicaid: 'bg-teal-100 text-teal-700',
}

export default function SendNoticeModal({ caseId, caseNumber, lob, amountAtRisk, onClose }: Props) {
  const today = new Date().toISOString().split('T')[0]
  const qc = useQueryClient()

  const [selectedTmpl,   setSelectedTmpl]   = useState<LetterTemplate | null>(null)
  const [renderedLetter, setRenderedLetter] = useState<RenderedLetter | null>(null)
  const [amountDemanded, setAmountDemanded] = useState(amountAtRisk.toFixed(2))
  const [deliveryMethod, setDeliveryMethod] = useState('mail')
  const [responseDue,    setResponseDue]    = useState(today)
  const [sendSuccess,    setSendSuccess]    = useState(false)
  const didAutoRender = useRef(false)

  const { data: templates = [], isLoading: loadingTemplates } = useQuery({
    queryKey: ['templates', lob],
    queryFn: () => getTemplates(lob),
  })

  // Mutation takes the template directly so we don't need to wait for state flush
  const renderMutation = useMutation({
    mutationFn: (tmpl: LetterTemplate) => renderLetter(caseId, tmpl.code),
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
      qc.invalidateQueries({ queryKey: ['case', caseId] })
      qc.invalidateQueries({ queryKey: ['notices', caseId] })
      setTimeout(() => onClose(), 1800)
    },
  })

  // Auto-select best matching template and trigger initial render
  useEffect(() => {
    if (templates.length === 0 || didAutoRender.current) return
    const best =
      templates.find((t) => t.template_type === 'initial_demand') ??
      templates.find((t) => t.template_type === 'second_notice') ??
      templates[0]
    didAutoRender.current = true
    setSelectedTmpl(best)
    renderMutation.mutate(best)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templates])

  function selectTemplate(t: LetterTemplate) {
    setSelectedTmpl(t)
    setRenderedLetter(null)
    renderMutation.mutate(t)
  }

  const canSend = selectedTmpl !== null && !!amountDemanded && !!responseDue && !sendSuccess

  return (
    <div
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-6xl flex flex-col overflow-hidden"
           style={{ height: '90vh' }}>

        {/* Modal header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 flex-shrink-0">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Send Recovery Notice</h2>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-sm text-gray-500">Case</span>
              <span className="font-mono font-semibold text-gray-800 text-sm">{caseNumber}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${LOB_PILL[lob] ?? 'bg-gray-100 text-gray-600'}`}>
                {lob}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-700 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex flex-1 min-h-0">

          {/* Left: template list */}
          <div className="w-56 flex-shrink-0 border-r border-gray-100 overflow-y-auto p-3 space-y-2">
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest px-1 pt-1 pb-2">
              {lob} Templates
            </p>
            {loadingTemplates ? (
              [...Array(3)].map((_, i) => (
                <div key={i} className="h-24 bg-gray-100 rounded-xl animate-pulse" />
              ))
            ) : templates.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-8">No templates for {lob}.</p>
            ) : (
              templates.map((t) => {
                const isSelected = selectedTmpl?.id === t.id
                return (
                  <div
                    key={t.id}
                    onClick={() => selectTemplate(t)}
                    className={`cursor-pointer rounded-xl transition-all duration-150 ${
                      isSelected
                        ? 'ring-2 ring-[#FE017D] shadow-sm'
                        : 'hover:shadow-sm opacity-70 hover:opacity-100'
                    }`}
                  >
                    <TemplateMetadata template={t} />
                    {isSelected && (
                      <div className="mx-4 mb-2 -mt-1">
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-[#FE017D] bg-pink-50 px-2 py-0.5 rounded-full border border-[#FE017D]/20">
                          ✓ Selected
                        </span>
                      </div>
                    )}
                  </div>
                )
              })
            )}
          </div>

          {/* Center: letter preview */}
          <div className="flex-1 min-w-0 overflow-y-auto p-5 bg-gray-50">
            <LetterViewer letter={renderedLetter} isLoading={renderMutation.isPending} />
          </div>

          {/* Right: controls */}
          <div className="w-60 flex-shrink-0 border-l border-gray-100 p-4 flex flex-col gap-3 overflow-y-auto">

            {/* Selected template callout */}
            {selectedTmpl ? (
              <div className="bg-pink-50 border border-[#FE017D]/25 rounded-xl p-3">
                <p className="text-[10px] font-bold text-[#FE017D] uppercase tracking-widest mb-1">
                  Template
                </p>
                <p className="text-sm font-semibold text-gray-900 leading-tight">{selectedTmpl.name}</p>
                <p className="font-mono text-xs text-gray-400 mt-0.5">{selectedTmpl.code}</p>
              </div>
            ) : (
              <div className="bg-gray-50 border border-gray-200 rounded-xl p-3 text-xs text-gray-400">
                No template selected
              </div>
            )}

            {/* Case ID — read only */}
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1">Case ID</label>
              <div className="px-3 py-2 bg-gray-100 border border-gray-200 rounded-lg text-sm font-mono text-gray-600 select-all">
                {caseId}
              </div>
            </div>

            {/* Amount Demanded */}
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1">Amount Demanded ($)</label>
              <input
                type="number"
                step="0.01"
                value={amountDemanded}
                onChange={(e) => setAmountDemanded(e.target.value)}
                className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm
                           focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]
                           transition-colors"
              />
            </div>

            {/* Delivery Method */}
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1">Delivery Method</label>
              <select
                value={deliveryMethod}
                onChange={(e) => setDeliveryMethod(e.target.value)}
                className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm
                           focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 transition-colors"
              >
                {['mail', 'fax', 'email', 'portal'].map((m) => (
                  <option key={m} value={m}>{m.charAt(0).toUpperCase() + m.slice(1)}</option>
                ))}
              </select>
            </div>

            {/* Response Due */}
            <div>
              <label className="text-xs font-medium text-gray-500 block mb-1">Response Due</label>
              <input
                type="date"
                value={responseDue}
                onChange={(e) => setResponseDue(e.target.value)}
                className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm
                           focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]
                           transition-colors"
              />
            </div>

            {/* Spacer */}
            <div className="flex-1" />

            {/* Re-preview */}
            <button
              onClick={() => selectedTmpl && renderMutation.mutate(selectedTmpl)}
              disabled={!selectedTmpl || renderMutation.isPending}
              className="w-full inline-flex items-center justify-center gap-2 px-3 py-2
                         border border-gray-200 text-gray-600 text-sm rounded-lg
                         hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed
                         transition-colors"
            >
              <Eye className="w-4 h-4" />
              {renderMutation.isPending ? 'Rendering…' : 'Re-preview'}
            </button>

            {/* Send Notice */}
            <button
              onClick={() => sendMutation.mutate()}
              disabled={!canSend || sendMutation.isPending}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5
                         bg-[#FE017D] text-white text-sm font-semibold rounded-lg
                         hover:bg-[#e5006f] disabled:opacity-40 disabled:cursor-not-allowed
                         transition-colors shadow-sm"
            >
              <Send className="w-4 h-4" />
              {sendMutation.isPending ? 'Sending…' : 'Send Notice'}
            </button>

            {sendSuccess && (
              <div className="flex items-center gap-1.5 text-xs text-green-700 bg-green-50
                              border border-green-200 rounded-lg px-3 py-2">
                <CheckCircle className="w-3.5 h-3.5 flex-shrink-0" />
                Notice sent! Closing…
              </div>
            )}
            {sendMutation.isError && (
              <p className="text-xs text-red-600 text-center">Failed to send. Please try again.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
