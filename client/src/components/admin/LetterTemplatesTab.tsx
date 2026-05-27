import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { FileText, Save, Eye, Lock, Edit3, CheckCircle } from 'lucide-react'
import api from '../../services/api'
import { useCurrentUser } from '../../hooks/useCurrentUser'

interface TemplateRead {
  id: string
  code: string
  name: string
  template_type: string
  lob: string
  version: number
  is_active: boolean
  created_at: string
  regulatory_reference: string
}

interface TemplateDetail extends TemplateRead {
  content_html: string
}

const LOB_PILL: Record<string, string> = {
  MA:       'bg-blue-100 text-blue-700',
  PPO:      'bg-purple-100 text-purple-700',
  Medicaid: 'bg-green-100 text-green-700',
}

const LOB_OPTIONS = ['All', 'MA', 'PPO', 'Medicaid']

export default function LetterTemplatesTab() {
  const { currentUser } = useCurrentUser()
  const isAdmin = currentUser?.role === 'admin'
  const queryClient = useQueryClient()

  const [lobFilter, setLobFilter] = useState<string>('All')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [editMode, setEditMode] = useState(false)

  // Form state
  const [draftName, setDraftName] = useState('')
  const [draftRegRef, setDraftRegRef] = useState('')
  const [draftContent, setDraftContent] = useState('')
  const [previewMode, setPreviewMode] = useState<'rendered' | 'source'>('rendered')

  const { data: templates = [], isLoading: loadingList } = useQuery<TemplateRead[]>({
    queryKey: ['letter-templates'],
    queryFn: async () => (await api.get<TemplateRead[]>('/letters/templates')).data,
  })

  const filtered = lobFilter === 'All'
    ? templates
    : templates.filter((t) => t.lob === lobFilter)

  // Auto-select first template when list loads
  useEffect(() => {
    if (filtered.length && !filtered.some((t) => t.id === selectedId)) {
      setSelectedId(filtered[0].id)
      setEditMode(false)
    }
  }, [filtered, selectedId])

  const { data: detail, isLoading: loadingDetail } = useQuery<TemplateDetail>({
    queryKey: ['letter-template', selectedId],
    queryFn: async () => (await api.get<TemplateDetail>(`/letters/templates/${selectedId}`)).data,
    enabled: !!selectedId,
  })

  // Reset drafts when detail loads or selection changes
  useEffect(() => {
    if (detail) {
      setDraftName(detail.name)
      setDraftRegRef(detail.regulatory_reference)
      setDraftContent(detail.content_html)
    }
  }, [detail])

  const saveMut = useMutation({
    mutationFn: async () =>
      api.patch<TemplateDetail>(`/letters/templates/${selectedId}`, {
        template_name: draftName,
        regulatory_reference: draftRegRef,
        content_html: draftContent,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['letter-templates'] })
      queryClient.invalidateQueries({ queryKey: ['letter-template', selectedId] })
      setEditMode(false)
    },
  })

  const isDirty =
    !!detail &&
    (draftName !== detail.name ||
      draftRegRef !== detail.regulatory_reference ||
      draftContent !== detail.content_html)

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-gray-900">Letter Templates</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            {isAdmin
              ? 'Edit the recovery-notice template for each line of business. Changes apply to all future notices.'
              : 'View the recovery-notice template for each line of business. Editing is restricted to admins.'
            }
          </p>
        </div>
        {!isAdmin && (
          <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-gray-500 bg-gray-100 border border-gray-200 px-2 py-1 rounded">
            <Lock className="w-3 h-3" /> Read only
          </span>
        )}
      </div>

      <div className="flex gap-4 items-start">
        {/* Left: LOB filter + template list */}
        <div className="w-72 flex-shrink-0 space-y-3">
          <div className="bg-white border border-gray-200 rounded-xl p-3">
            <label className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block mb-1.5">
              Filter by LOB
            </label>
            <select
              value={lobFilter}
              onChange={(e) => setLobFilter(e.target.value)}
              className="w-full px-3 py-2 text-sm bg-white border border-gray-200 rounded-lg focus:outline-none focus:border-[#FE017D] focus:ring-1 focus:ring-[#FE017D]/30"
            >
              {LOB_OPTIONS.map((o) => <option key={o} value={o}>{o}{o !== 'All' ? ' only' : ''}</option>)}
            </select>
          </div>

          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            {loadingList ? (
              <div className="p-3 space-y-2 animate-pulse">
                {[...Array(3)].map((_, i) => <div key={i} className="h-20 bg-gray-100 rounded" />)}
              </div>
            ) : filtered.length === 0 ? (
              <p className="p-4 text-sm text-gray-400 italic">No templates match.</p>
            ) : (
              <ul className="divide-y divide-gray-100">
                {filtered.map((t) => {
                  const active = t.id === selectedId
                  return (
                    <li key={t.id}>
                      <button
                        onClick={() => { setSelectedId(t.id); setEditMode(false) }}
                        className={`w-full text-left p-3 transition-colors ${
                          active ? 'bg-pink-50' : 'hover:bg-gray-50'
                        }`}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-mono text-[11px] font-semibold text-gray-500">{t.code}</span>
                          {t.is_active ? (
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-green-100 text-green-700">Active</span>
                          ) : (
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-gray-200 text-gray-600">Inactive</span>
                          )}
                        </div>
                        <p className={`text-sm leading-snug ${active ? 'font-semibold text-[#FE017D]' : 'font-medium text-gray-800'}`}>
                          {t.name}
                        </p>
                        <div className="flex items-center gap-1.5 mt-1.5">
                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${LOB_PILL[t.lob] ?? 'bg-gray-100 text-gray-600'}`}>
                            {t.lob}
                          </span>
                          <span className="text-[10px] font-mono text-gray-400">v{t.version}</span>
                        </div>
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </div>

        {/* Right: detail / editor */}
        <div className="flex-1 min-w-0 bg-white border border-gray-200 rounded-xl">
          {!detail || loadingDetail ? (
            <div className="p-8 text-center">
              <FileText className="w-10 h-10 text-gray-300 mx-auto mb-2" />
              <p className="text-sm text-gray-400">Select a template to view.</p>
            </div>
          ) : (
            <>
              {/* Header */}
              <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between gap-3">
                <div className="min-w-0 flex-1">
                  {editMode && isAdmin ? (
                    <input
                      type="text"
                      value={draftName}
                      onChange={(e) => setDraftName(e.target.value)}
                      className="w-full text-sm font-bold text-gray-900 px-2 py-1 border border-gray-200 rounded focus:outline-none focus:border-indigo-400"
                    />
                  ) : (
                    <p className="text-sm font-bold text-gray-900 truncate">{detail.name}</p>
                  )}
                  <p className="text-[11px] text-gray-400 font-mono mt-0.5">
                    {detail.code} · {detail.lob} · v{detail.version}
                  </p>
                </div>
                {isAdmin && (
                  editMode ? (
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {saveMut.isSuccess && !isDirty && (
                        <span className="text-xs text-green-600 inline-flex items-center gap-1">
                          <CheckCircle className="w-3 h-3" /> Saved
                        </span>
                      )}
                      <button
                        onClick={() => { setEditMode(false); setDraftName(detail.name); setDraftRegRef(detail.regulatory_reference); setDraftContent(detail.content_html) }}
                        className="px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-200 rounded hover:bg-gray-50"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => saveMut.mutate()}
                        disabled={!isDirty || saveMut.isPending}
                        className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold bg-[#FE017D] hover:bg-[#e5006f] text-white rounded disabled:bg-gray-200 disabled:text-gray-400"
                      >
                        <Save className="w-3 h-3" />
                        {saveMut.isPending ? 'Saving…' : 'Save changes'}
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setEditMode(true)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold bg-white text-indigo-700 border border-indigo-200 rounded hover:bg-indigo-50"
                    >
                      <Edit3 className="w-3 h-3" /> Edit template
                    </button>
                  )
                )}
              </div>

              {/* Regulatory reference */}
              <div className="px-5 py-2.5 border-b border-gray-100 bg-gray-50">
                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-0.5">
                  Regulatory Reference
                </p>
                {editMode && isAdmin ? (
                  <input
                    type="text"
                    value={draftRegRef}
                    onChange={(e) => setDraftRegRef(e.target.value)}
                    className="w-full text-sm text-gray-800 px-2 py-1 border border-gray-200 rounded focus:outline-none focus:border-indigo-400 bg-white"
                  />
                ) : (
                  <p className="text-sm text-gray-700">{detail.regulatory_reference || <span className="text-gray-400 italic">none</span>}</p>
                )}
              </div>

              {/* Content body */}
              <div className="p-5">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Template Content</p>
                  {!editMode && (
                    <div className="inline-flex bg-gray-100 rounded p-0.5">
                      <button
                        onClick={() => setPreviewMode('rendered')}
                        className={`px-2 py-0.5 text-[11px] font-semibold rounded ${
                          previewMode === 'rendered' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'
                        }`}
                      >
                        <Eye className="w-3 h-3 inline mr-1" /> Rendered
                      </button>
                      <button
                        onClick={() => setPreviewMode('source')}
                        className={`px-2 py-0.5 text-[11px] font-semibold rounded ${
                          previewMode === 'source' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'
                        }`}
                      >
                        HTML source
                      </button>
                    </div>
                  )}
                </div>

                {editMode && isAdmin ? (
                  <>
                    <textarea
                      value={draftContent}
                      onChange={(e) => setDraftContent(e.target.value)}
                      className="w-full font-mono text-xs px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100"
                      style={{ minHeight: '24rem', resize: 'vertical' }}
                      spellCheck={false}
                    />
                    <p className="text-[11px] text-gray-400 mt-1.5">
                      HTML allowed. Variables like <code className="font-mono">{'{{ case_number }}'}</code> are filled at render time.
                    </p>
                  </>
                ) : (
                  <div className="bg-gray-50 border border-gray-100 rounded-lg p-4 max-h-[28rem] overflow-y-auto">
                    {previewMode === 'rendered' ? (
                      <div
                        className="prose prose-sm max-w-none"
                        dangerouslySetInnerHTML={{ __html: detail.content_html }}
                      />
                    ) : (
                      <pre className="font-mono text-xs text-gray-700 whitespace-pre-wrap">
                        {detail.content_html}
                      </pre>
                    )}
                  </div>
                )}

                {saveMut.isError && (
                  <p className="text-xs text-red-600 mt-2">
                    {(saveMut.error as any)?.response?.data?.detail ?? 'Failed to save'}
                  </p>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
