// Lightweight app-access check. Fetches the current user's full profile
// (which includes RBAC roles[] + apps[]) and tells the caller whether the
// current user has access to a named app.
//
// Soft check: the data layer enforces nothing here. We just give the UI
// the info it needs to render a "no access" page instead of the real app.
// Once the unified backend adds per-route enforcement (require_app()),
// the UI will additionally get 403s — both paths converge on the same UX.
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { useCurrentUser } from './useCurrentUser'

interface UserWithRbac {
  id: string
  name: string
  role: string
  is_active: boolean
  roles: string[]
  apps: string[]
  default_app: string | null
}

export interface AppAccess {
  isLoading: boolean
  hasAccess: boolean
  userApps: string[]
  userRoles: string[]
  reason: string | null
}

/** Hook: does the current user have access to the given app? */
export function useAppAccess(appName: string): AppAccess {
  const { currentUser, isLoading: userBootLoading } = useCurrentUser()

  const profileQ = useQuery({
    queryKey: ['user-rbac', currentUser?.id],
    queryFn: async () => {
      const res = await api.get<UserWithRbac>(`/users/${currentUser!.id}`)
      return res.data
    },
    enabled: !!currentUser?.id,
    staleTime: 60_000,
  })

  // While the bootstrap picker is fetching the user list, don't render the
  // no-access page yet — show a loading state.
  if (userBootLoading) {
    return { isLoading: true, hasAccess: false, userApps: [], userRoles: [], reason: null }
  }
  if (!currentUser) {
    return {
      isLoading: false,
      hasAccess: false,
      userApps: [],
      userRoles: [],
      reason: 'No user selected. Pick a user from the top bar.',
    }
  }
  if (profileQ.isLoading || !profileQ.data) {
    return { isLoading: true, hasAccess: false, userApps: [], userRoles: [], reason: null }
  }
  const data = profileQ.data
  const hasAccess = data.apps.includes(appName)
  return {
    isLoading: false,
    hasAccess,
    userApps: data.apps,
    userRoles: data.roles,
    reason: hasAccess
      ? null
      : `Your roles (${data.roles.join(', ') || 'none'}) do not grant access to the '${appName}' app.`,
  }
}
