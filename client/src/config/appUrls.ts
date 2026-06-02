// Central URL config for the platform suite (PayGuard / SIU / ClaimGuard / IAM /
// Assistant + the backend API).
//
// Values are COMMITTED here and switch automatically by Vite build mode:
//   `npm run dev`                → DEV  (localhost ports)
//   `npm run build` (production) → PROD (penguinai.studio hosts)
//
// This deliberately does NOT read `import.meta.env.VITE_*`. The URLs live in
// code, not in the Railway dashboard — so a missing/stale platform variable can
// never silently break the links. `import.meta.env.PROD` is set by Vite from the
// build mode itself, not by any deployment variable.
//
// To change a URL: edit the map below and redeploy. No env vars to manage.
const PROD = {
  apiBase:    'https://payguard.penguinai.studio',
  iam:        'https://iam.penguinai.studio',
  payguard:   'https://payguard.penguinai.studio',
  siu:        'https://siu.penguinai.studio',
  claimguard: 'https://claimguard.penguinai.studio',
  assistant:  'https://assistant.penguinai.studio',
} as const

const DEV = {
  apiBase:    'http://localhost:8001',
  iam:        'http://localhost:5177',
  payguard:   'http://localhost:5174',
  siu:        'http://localhost:5178',
  claimguard: 'http://localhost:5175',
  assistant:  'http://localhost:5179',
} as const

const CFG = import.meta.env.PROD ? PROD : DEV

/** Backend API root — no trailing slash, no `/api` suffix. */
export const API_BASE_URL = CFG.apiBase

export const APP_URLS = {
  iam:        CFG.iam,
  payguard:   CFG.payguard,
  claimguard: CFG.claimguard,
  siu:        CFG.siu,
  assistant:  CFG.assistant,
} as const

export type AppKey = keyof typeof APP_URLS

/** Build a deep link into another app, joining the base URL with a path. */
export function appUrl(app: AppKey, path = ''): string {
  const base = APP_URLS[app].replace(/\/$/, '')
  if (!path) return base
  return `${base}/${path.replace(/^\//, '')}`
}
