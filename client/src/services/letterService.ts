import api from './api'
import type { LetterTemplate, LetterTemplateDetail, RenderedLetter, RecoveryNotice } from '../types'

export async function getTemplates(lob?: string): Promise<LetterTemplate[]> {
  const params: Record<string, string> = {}
  if (lob) params.lob = lob
  const res = await api.get<LetterTemplate[]>('/letters/templates', { params })
  return res.data
}

export async function getTemplate(code: string): Promise<LetterTemplateDetail> {
  const res = await api.get<LetterTemplateDetail>(`/letters/templates/${code}`)
  return res.data
}

export async function renderLetter(
  caseId: number,
  templateCode: string
): Promise<RenderedLetter> {
  const res = await api.post<RenderedLetter>('/letters/render', {
    case_id: caseId,
    template_code: templateCode,
  })
  return res.data
}

export async function sendNotice(data: {
  case_id: number
  template_id: string
  amount_demanded: number
  delivery_method: string
  response_due: string
}): Promise<RecoveryNotice> {
  const res = await api.post<RecoveryNotice>('/letters/notices', data)
  return res.data
}

export async function getNotices(caseId: number): Promise<RecoveryNotice[]> {
  const res = await api.get<RecoveryNotice[]>(`/cases/${caseId}/notices`)
  return res.data
}
