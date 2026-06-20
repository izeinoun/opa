import api from './api'

/** A document saved on a case (e.g. a generated recoupment letter). */
export interface CaseDocument {
  id: string
  claim_id: string | null
  case_id: string | null
  filename: string
  file_size_kb: number
  kind: string
  uploaded_at: string
  uploaded_by_user_id: string | null
}

/** A system-generated output document surfaced in the Intake Portal. */
export interface OutputFile {
  document_id: string
  filename: string
  kind: string
  case_id: string | null
  case_number: string | null
  case_sequence: number | null
  uploaded_at: string
  file_size_kb: number
}

/** Generate the provider recoupment letter PDF for a case (by case sequence). */
export async function generateRecoupmentLetter(caseSeq: number): Promise<CaseDocument> {
  const res = await api.post<CaseDocument>(`/cases/${caseSeq}/recoupment-letter`)
  return res.data
}

/** List recoupment letters already generated for a case (by case UUID). */
export async function listCaseLetters(caseId: string): Promise<CaseDocument[]> {
  const res = await api.get<CaseDocument[]>('/documents', {
    params: { case_id: caseId, kind: 'recoupment_letter' },
  })
  return res.data
}

/** List all generated output files (recoupment letters) for the Intake Portal. */
export async function listOutputFiles(): Promise<OutputFile[]> {
  const res = await api.get<OutputFile[]>('/file-intake/outputs')
  return res.data
}
