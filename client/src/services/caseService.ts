import api from './api'
import type {
  CaseListResponse,
  CaseDetail,
  AuditLog,
  CaseStatus,
  WorklistFilters,
} from '../types'

export async function getCases(filters: WorklistFilters): Promise<CaseListResponse> {
  const params: Record<string, string | number | boolean> = {}
  if (filters.status) params.status = filters.status
  if (filters.priority) params.priority = filters.priority
  if (filters.lob) params.lob = filters.lob
  if (filters.page !== undefined) params.page = filters.page
  if (filters.page_size !== undefined) params.page_size = filters.page_size
  if (filters.exclude_closed) params.exclude_closed = true
  if (filters.closed_only) params.closed_only = true
  if (filters.overdue_only) params.overdue_only = true
  if (filters.search) params.search = filters.search

  const res = await api.get<CaseListResponse>('/cases', { params })
  return res.data
}

export async function getCase(caseId: number): Promise<CaseDetail> {
  const res = await api.get<CaseDetail>(`/cases/${caseId}`)
  return res.data
}

export async function transitionCase(
  caseId: number,
  data: { to_status: CaseStatus; notes?: string }
): Promise<CaseDetail> {
  const res = await api.post<CaseDetail>(`/cases/${caseId}/transition`, data)
  return res.data
}

export async function reopenCase(caseId: number, reason: string): Promise<CaseDetail> {
  const res = await api.post<CaseDetail>(`/cases/${caseId}/reopen`, { reason })
  return res.data
}

export async function getAuditLog(caseId: number): Promise<AuditLog[]> {
  const res = await api.get<AuditLog[]>(`/cases/${caseId}/audit-log`)
  return res.data
}
