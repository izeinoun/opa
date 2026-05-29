import { ReactNode } from 'react'
import { ShieldX } from 'lucide-react'
import { useAppAccess } from '../../hooks/useAppAccess'

interface Props {
  appName: string
  children: ReactNode
}

/** Renders children only if the current user has RBAC access to appName.
 *  Otherwise shows a friendly explanation page. */
export default function NoAccessGate({ appName, children }: Props) {
  const access = useAppAccess(appName)

  if (access.isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-400">
        Checking access…
      </div>
    )
  }
  if (access.hasAccess) return <>{children}</>

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="max-w-md text-center">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-amber-50 text-amber-600 mb-4">
          <ShieldX className="w-7 h-7" />
        </div>
        <h1 className="text-2xl font-semibold text-slate-900 mb-2">
          You don't have access to this app
        </h1>
        <p className="text-sm text-slate-600 mb-4">
          {access.reason}
        </p>
        <p className="text-xs text-slate-500">
          Apps you currently have access to:{' '}
          <span className="font-medium text-slate-700">
            {access.userApps.length === 0 ? 'none' : access.userApps.join(', ')}
          </span>
        </p>
        <p className="text-xs text-slate-400 mt-6">
          Ask an administrator to grant you the appropriate role in the IAM admin app.
        </p>
      </div>
    </div>
  )
}
