// Walkthrough types — mirror of server/app/schemas/walkthrough.py.
// The backend is the single source of truth for tour copy + ordering; this is
// just the shape the shared spotlight engine renders.

export interface TourAppLink {
  app: string      // AppKey known to config/appUrls: payguard|claimguard|siu|...
  label: string
  path?: string
}

export interface TourStep {
  key: string
  title: string
  body: string
  anchor?: string | null       // data-tour="<anchor>" to spotlight; null => centered card
  placement?: string           // top|bottom|left|right|center|auto
  route?: string | null        // in-app path to navigate to before showing this step
  app_links?: TourAppLink[]
}

export interface Tour {
  app: string
  role: string
  role_label: string
  version: number
  steps: TourStep[]
}
