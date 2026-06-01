/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Backend API base URL (consumed in src/services/api.ts). Optional — falls
  // back to the relative `/api` path (Vite proxy / same-origin) when unset.
  readonly VITE_API_URL?: string
  // Cross-app URLs (consumed in src/config/appUrls.ts). Optional — each falls
  // back to its pinned local dev port when unset.
  readonly VITE_IAM_URL?: string
  readonly VITE_PAYGUARD_URL?: string
  readonly VITE_CLAIMGUARD_URL?: string
  readonly VITE_SIU_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
