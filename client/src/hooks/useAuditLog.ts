import { useQuery } from '@tanstack/react-query'
import { getAuditLog } from '../services/caseService'
import type { AuditLog } from '../types'

export function useAuditLog(caseId: number) {
  return useQuery<AuditLog[], Error>({
    queryKey: ['auditLog', caseId],
    queryFn: () => getAuditLog(caseId),
    enabled: caseId > 0,
  })
}
