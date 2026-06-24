// Case-guidance types — mirror of server/app/schemas/guidance.py.
// Shared by the PayGuard case page and the Assistant cockpit so both surfaces
// render the same lifecycle + next-action. See docs/workflow-guidance-plan.md.

export type LifecycleStepState =
  | 'completed'
  | 'current'
  | 'blocked'
  | 'upcoming'
  | 'skipped'

export interface LifecycleStep {
  key: string
  label: string
  state: LifecycleStepState
  detail?: string | null
  conditional?: boolean
}

export interface NextAction {
  kind: string          // semantic action id (see case_guidance_service.py)
  label: string
  explanation: string
  actionable?: boolean
  target?: {
    view?: string
    params?: Record<string, unknown>
  }
}

export interface Blocker {
  type: string
  count: number
  message: string
}

export interface RoleContext {
  is_owner: boolean
  role: string
  supervisor_gate: boolean
}

export interface CaseGuidance {
  lifecycle: LifecycleStep[]
  current_step?: string | null
  next_action?: NextAction | null
  blockers: Blocker[]
  remaining_summary: string
  role_context: RoleContext
}
