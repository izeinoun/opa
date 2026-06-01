// Evidence-related API calls: document upload/list, AI evidence findings.
// Backed by the unified backend endpoints added in Phase-3 + follow-ups.
import api, { API_BASE } from './api'

export interface EvidenceDocument {
  id: string
  claim_id: string | null
  case_id: string | null
  filename: string
  file_size_kb: number
  kind: 'claim_form' | 'supporting' | 'medical_record'
  uploaded_at: string
  uploaded_by_user_id: string | null
}

export interface EvidenceFinding {
  id: string
  claim_id: string
  code: string | null
  severity: 'critical' | 'warning' | 'ok'
  title: string | null
  body: string
  created_at: string
}

export interface ValidateEvidenceResponse {
  claim_id: string
  chart_text_chars: number
  findings: EvidenceFinding[]
}

export const evidenceService = {
  async listDocuments(claimId: string): Promise<EvidenceDocument[]> {
    const { data } = await api.get<EvidenceDocument[]>('/documents', {
      params: { claim_id: claimId },
    })
    return data
  },

  async uploadDocument(
    claimId: string,
    file: File,
    kind: 'supporting' | 'medical_record' = 'medical_record',
    userId?: string,
  ): Promise<EvidenceDocument> {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('claim_id', claimId)
    fd.append('kind', kind)
    if (userId) fd.append('user_id', userId)
    const { data } = await api.post<EvidenceDocument>('/documents', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 90_000,
    })
    return data
  },

  async deleteDocument(documentId: string): Promise<void> {
    await api.delete(`/documents/${documentId}`)
  },

  downloadUrl(documentId: string): string {
    return `${API_BASE}/documents/${documentId}/download`
  },

  async listEvidenceFindings(claimId: string): Promise<EvidenceFinding[]> {
    const { data } = await api.get<EvidenceFinding[]>(
      `/claims/${claimId}/evidence-findings`,
    )
    return data
  },

  async runValidateEvidence(claimId: string): Promise<ValidateEvidenceResponse> {
    const { data } = await api.post<ValidateEvidenceResponse>(
      `/claims/${claimId}/validate-evidence`,
      {},
      { timeout: 90_000 },
    )
    return data
  },
}
