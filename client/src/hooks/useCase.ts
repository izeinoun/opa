import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getCase, transitionCase, reopenCase } from '../services/caseService'
import type { CaseDetail, CaseStatus } from '../types'

export function useCase(caseId: number) {
  const queryClient = useQueryClient()

  const query = useQuery<CaseDetail, Error>({
    queryKey: ['case', caseId],
    queryFn: () => getCase(caseId),
    enabled: caseId > 0,
  })

  const mutateTransition = useMutation<
    CaseDetail,
    Error,
    { to_status: CaseStatus; notes?: string }
  >({
    mutationFn: (data) => transitionCase(caseId, data),
    onSuccess: (updated) => {
      queryClient.setQueryData(['case', caseId], updated)
      queryClient.invalidateQueries({ queryKey: ['cases'] })
    },
  })

  const mutateReopen = useMutation<CaseDetail, Error, string>({
    mutationFn: (reason) => reopenCase(caseId, reason),
    onSuccess: (updated) => {
      queryClient.setQueryData(['case', caseId], updated)
      queryClient.invalidateQueries({ queryKey: ['cases'] })
    },
  })

  return {
    data: query.data,
    isLoading: query.isLoading,
    error: query.error,
    refetch: query.refetch,
    mutateTransition,
    mutateReopen,
  }
}
