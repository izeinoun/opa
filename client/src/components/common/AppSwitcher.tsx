// Cross-app switcher shown in the top bar. Links to the other platform apps.
// URLs are env-overridable (set per deployment); fallbacks are the pinned
// local dev ports for each app.
import { ClipboardCheck, KeyRound, ShieldCheck, Siren } from 'lucide-react'

const ENV = import.meta.env as Record<string, string | undefined>

const APPS = [
  { key: 'iam',        label: 'IAM Admin',  href: ENV.VITE_IAM_URL        ?? 'http://localhost:5177', icon: KeyRound },
  { key: 'payguard',   label: 'PayGuard',   href: ENV.VITE_PAYGUARD_URL   ?? 'http://localhost:5174', icon: ShieldCheck },
  { key: 'claimguard', label: 'ClaimGuard', href: ENV.VITE_CLAIMGUARD_URL ?? 'http://localhost:5175', icon: ClipboardCheck },
  { key: 'siu',        label: 'SIU',        href: ENV.VITE_SIU_URL        ?? 'http://localhost:5178', icon: Siren },
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
