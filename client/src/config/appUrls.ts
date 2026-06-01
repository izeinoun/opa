// Cross-app URLs for the platform suite. Each app is deployed separately, so the
// links between them differ per environment (localhost in dev, real hosts in prod).
//
// Values are read from Vite env vars (VITE_*_URL) with the pinned local dev ports
// as fallbacks. Set the env vars per deployment — see client/.env.example.
//
// NOTE: Vite inlines `import.meta.env.*` at BUILD time, so these must be present
// when `npm run build` runs (e.g. as Railway build-time env vars), not at runtime.
const ENV = import.meta.env as Record<string, string | undefined>

export const APP_URLS = {
  iam:        ENV.VITE_IAM_URL        ?? 'http://localhost:5177',
  payguard:   ENV.VITE_PAYGUARD_URL   ?? 'http://localhost:5174',
  claimguard: ENV.VITE_CLAIMGUARD_URL ?? 'http://localhost:5175',
  siu:        ENV.VITE_SIU_URL        ?? 'http://localhost:5178',
} as const

export type AppKey = keyof typeof APP_URLS

// Build a deep link into another app, joining the base URL with a path.
export function appUrl(app: AppKey, path = ''): string {
  const base = APP_URLS[app].replace(/\/$/, '')
  if (!path) return base
  return `${base}/${path.replace(/^\//, '')}`
}
