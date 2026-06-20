import api from './api'

export type IntakeApp = 'payguard' | 'claimguard'
export type IntakeCategory = '835' | '837' | 'medical' | 'claim_pdf'
export type IntakeStatus =
  | 'pending' | 'case_created' | 'linked' | 'unmatched' | 'rejected' | 'error'

export interface ExtractedServiceLine {
  cpt: string | null
  date: string | null
}

export interface IntakeFile {
  intake_id: string
  app: IntakeApp
  category: IntakeCategory
  filename: string
  file_size_kb: number
  uploaded_at: string
  uploaded_by_user_id: string | null
  extraction_status: string | null
  extracted_member_number: string | null
  extracted_member_name: string | null
  extracted_dob: string | null
  extracted_service_dates: string[]
  extracted_service_lines: ExtractedServiceLine[]
  status: IntakeStatus
  candidate_case_ids: string[]
  message: string | null
  result_case_id: string | null
  result_claim_id: string | null
  result_document_id: string | null
  result_case_number: string | null
  created_at: string
  updated_at: string
}

export interface CandidateCase {
  case_id: string
  case_number: string
  member_name: string | null
  service_from_date: string | null
  service_to_date: string | null
  priority: string | null
  status: string
  total_overpayment_amount: number | null
}

export interface UnmatchedFile extends IntakeFile {
  candidates: CandidateCase[]
}

export async function uploadIntake(
  file: File, app: IntakeApp, category: IntakeCategory,
): Promise<IntakeFile> {
  const form = new FormData()
  form.append('file', file)
  form.append('app', app)
  form.append('category', category)
  const res = await api.post<IntakeFile>('/file-intake/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function listIntake(params?: {
  app?: IntakeApp; category?: IntakeCategory; status?: IntakeStatus
}): Promise<IntakeFile[]> {
  const res = await api.get<IntakeFile[]>('/file-intake', { params })
  return res.data
}

export async function listUnmatched(): Promise<UnmatchedFile[]> {
  const res = await api.get<UnmatchedFile[]>('/file-intake/unmatched')
  return res.data
}

export async function resolveIntake(intakeId: string, caseId: string): Promise<IntakeFile> {
  const res = await api.post<IntakeFile>(`/file-intake/${intakeId}/resolve`, { case_id: caseId })
  return res.data
}

export async function deleteIntake(intakeId: string): Promise<void> {
  await api.delete(`/file-intake/${intakeId}`)
}
