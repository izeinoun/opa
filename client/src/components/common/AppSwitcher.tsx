// Cross-app switcher shown in the top bar. Links to the other platform apps.
// URLs come from the central appUrls config (env-overridable per deployment).
import { ClipboardCheck, KeyRound, ShieldCheck, Siren } from 'lucide-react'
import { APP_URLS } from '../../config/appUrls'

const APPS = [
  { key: 'iam',        label: 'IAM Admin',  href: APP_URLS.iam,        icon: KeyRound },
  { key: 'payguard',   label: 'PayGuard',   href: APP_URLS.payguard,   icon: ShieldCheck },
  { key: 'claimguard', label: 'ClaimGuard', href: APP_URLS.claimguard, icon: ClipboardCheck },
  { key: 'siu',        label: 'SIU',        href: APP_URLS.siu,        icon: Siren },
]

export default function AppSwitcher({ current }: { current: string }) {
  return (
    <nav className="flex items-center gap-1" aria-label="Applications">
      {APPS.filter((a) => a.key !== current).map(({ key, label, href, icon: Icon }) => (
        <a
          key={key}
          href={href}
          title={`Open ${label}`}
          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm text-gray-500 hover:bg-gray-100 hover:text-gray-900 transition-colors"
        >
          <Icon className="w-4 h-4" />
          <span className="hidden lg:inline">{label}</span>
        </a>
      ))}
    </nav>
  )
}
