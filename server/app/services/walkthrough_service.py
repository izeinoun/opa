"""Walkthrough composer — the single source of truth for the new-user tour.

A tour is assembled from small REUSABLE fragments (intro, per-app core,
role overlays, outro) rather than authored end-to-end per (app, role). Adding
a step, fixing copy, or reordering happens here once; every SPA that embeds the
shared spotlight engine picks it up with no frontend redeploy.

Tailoring has two axes:
  * app   — which product the caller is in (payguard | claimguard | siu | intake)
  * role  — the caller's persona, chosen from their RBAC roles (see `persona_for`)

Cross-app "explore the rest of the suite" steps only link apps the caller can
actually reach, so the tour never dangles a walled-off door.
"""
from __future__ import annotations

from typing import List, Set

from ..schemas.walkthrough import Tour, TourStep, TourAppLink

# ── Personas ────────────────────────────────────────────────────────────────
# Human labels for the role a tour was tailored to.
ROLE_LABELS = {
    "admin": "Administrator",
    "supervisor": "Supervisor",
    "analyst": "Analyst",
    "specialist": "Claims Specialist",
    "siu_investigator": "SIU Investigator",
    "recoupment_specialist": "Recoupment Specialist",
    "intake": "Intake Operator",
    "system": "System",
}

# Given a caller with (possibly several) roles, which persona's tour do we show
# inside each app? Most-specific-for-this-app wins, falling back down the list.
_APP_PERSONA_PRIORITY = {
    "payguard":   ["admin", "supervisor", "recoupment_specialist", "analyst"],
    "claimguard": ["admin", "supervisor", "specialist", "analyst"],
    "siu":        ["admin", "supervisor", "siu_investigator"],
    "intake":     ["admin", "intake"],
    # IAM is an admin surface; the Assistant is cross-cutting (anyone can use it),
    # so label its tour with whatever the caller's primary role is.
    "iam":        ["admin", "supervisor", "analyst"],
    "assistant":  ["admin", "supervisor", "siu_investigator", "recoupment_specialist",
                   "specialist", "analyst"],
}

# Apps that have a first-class SPA we can deep-link into from an outro step.
# (cob has no UI yet; the secure intake portal is a separate host.)
_LINKABLE_APPS = {
    "payguard":   TourAppLink(app="payguard", label="PayGuard — post-pay recovery"),
    "claimguard": TourAppLink(app="claimguard", label="ClaimGuard — pre-pay review"),
    "siu":        TourAppLink(app="siu", label="SIU — investigations"),
}


def persona_for(app: str, role_names: Set[str]) -> str:
    """Pick the persona whose tour best fits this caller in this app."""
    for role in _APP_PERSONA_PRIORITY.get(app, []):
        if role in role_names:
            return role
    # Caller can reach the app but holds none of its "native" roles (e.g. an
    # admin-adjacent account). Default to the app's baseline reviewer persona.
    return {"siu": "siu_investigator", "intake": "intake"}.get(app, "analyst")


# ── Reusable fragments ────────────────────────────────────────────────────────
# Each helper returns a list of steps. The composer stitches them together and
# only then are step `key`s guaranteed unique (they already are by construction).

def _intro(app_label: str) -> List[TourStep]:
    return [
        TourStep(
            key="welcome",
            title=f"Welcome to {app_label}",
            body=(
                "This quick tour shows you around. It takes about a minute — "
                "you can exit anytime and replay it from the ? button in the top bar."
            ),
            placement="center",
        ),
        TourStep(
            key="identity",
            title="This is you",
            body=(
                "Your role decides what you can see and do across the suite. "
                "In the demo you can switch identities here to see the app through "
                "someone else's permissions."
            ),
            anchor="user-menu",
            placement="bottom",
        ),
        TourStep(
            key="suite",
            title="One app in a suite",
            body=(
                f"{app_label} is one product in the payment-integrity platform. "
                "Use this switcher to jump between the apps your role grants."
            ),
            anchor="app-switcher",
            placement="bottom",
        ),
    ]


def _outro(role_label: str, other_apps: List[TourAppLink]) -> List[TourStep]:
    steps = [
        TourStep(
            key="replay",
            title="Replay anytime",
            body="Click the ? in the top bar whenever you want to run this tour again.",
            anchor="help-tour",
            placement="bottom",
        )
    ]
    body = f"That's the {role_label} tour. "
    if other_apps:
        body += "You also have access to the apps below — open one to keep exploring. "
    body += "And the Assistant (chat) can answer questions or take actions for you."
    steps.append(
        TourStep(
            key="finish",
            title="You're ready",
            body=body,
            placement="center",
            app_links=other_apps,
        )
    )
    return steps


# ── Per-app core tours ────────────────────────────────────────────────────────

def _payguard_core() -> List[TourStep]:
    return [
        TourStep(
            key="pipeline",
            title="Work follows the case lifecycle",
            body="Your navigation is organized by stage: Intake → Review → Recovery → Closed.",
            anchor="main-nav",
            placement="right",
        ),
        TourStep(
            key="intake",
            title="New cases land in Intake",
            body="Claims our detectors flag show up here as cases, ranked by expected recovery value.",
            anchor="nav-intake",
            placement="right",
        ),
        TourStep(
            key="review",
            title="Review is your worklist",
            body=(
                "Open a case here to see the claim, the detector findings that flagged it, "
                "its evidence score, and the recommended next action. You can run AI analysis "
                "and draft a provider recovery letter from inside the case."
            ),
            anchor="nav-review",
            placement="right",
        ),
        TourStep(
            key="recovery",
            title="Recovery closes the loop",
            body=(
                "Once a notice is sent, cases move to Recovery — you track the provider's "
                "response and reconcile it against the inbound 835 remittance."
            ),
            anchor="nav-recovery",
            placement="right",
        ),
        TourStep(
            key="reference",
            title="Reference data backs every finding",
            body="Members, providers, and fee schedules are the source of truth the detectors score against.",
            anchor="nav-members",
            placement="right",
        ),
    ]


def _claimguard_core() -> List[TourStep]:
    return [
        TourStep(
            key="claims",
            title="Review happens BEFORE payment",
            body="ClaimGuard checks claims pre-pay. The Claims queue is your worklist of incoming claims.",
            anchor="nav-claims",
            placement="right",
        ),
        TourStep(
            key="new-claim",
            title="Bring a claim in",
            body=(
                "Submit a claim — or drop a PDF/UB-04/CMS-1500 — and Claude extracts the codes "
                "and runs the review rules for you before anything is paid."
            ),
            placement="center",
        ),
        TourStep(
            key="claim-detail",
            title="Decide with the evidence in front of you",
            body=(
                "Open a claim to see extracted lines, the findings, and the AI summary, then "
                "approve, deny, or send it back — all before a dollar goes out."
            ),
            anchor="nav-claims",
            placement="right",
        ),
        TourStep(
            key="reports",
            title="See the numbers",
            body="Reports roll up review outcomes and dollars saved across the queue.",
            anchor="nav-reports",
            placement="right",
        ),
    ]


def _siu_core() -> List[TourStep]:
    return [
        TourStep(
            key="dashboard",
            title="Start at the Dashboard",
            body="Your Dashboard rolls up team and case metrics so you can see where the unit stands.",
            anchor="nav-dashboard",
            placement="right",
        ),
        TourStep(
            key="post-pay",
            title="Post-pay investigations",
            body=(
                "The Post-pay queue holds PayGuard cases escalated to SIU. Open one to investigate — "
                "add notes, attach evidence, and file law-enforcement or regulator referrals."
            ),
            anchor="nav-post-pay",
            placement="right",
        ),
        TourStep(
            key="pre-pay",
            title="Pre-pay investigations",
            body="The Pre-pay queue holds ClaimGuard cases flagged for fraud, waste & abuse before payment.",
            anchor="nav-pre-pay",
            placement="right",
        ),
    ]


def _intake_core() -> List[TourStep]:
    return [
        TourStep(
            key="drop",
            title="Drop files securely",
            body="This portal ingests claim files into the platform. Upload here and the pipeline picks them up.",
            anchor="nav-upload",
            placement="right",
        ),
    ]


def _assistant_core() -> List[TourStep]:
    return [
        TourStep(
            key="chat",
            title="Ask in plain English",
            body=(
                "This whole screen is a chat cockpit. Ask about cases, providers, or metrics and "
                "the Assistant pulls live data for you — no need to know where anything lives."
            ),
            placement="center",
        ),
        TourStep(
            key="actions",
            title="It can act, not just answer",
            body=(
                "Beyond answering, the Assistant can take actions on your behalf — and it always "
                "shows you what it's about to do and asks for confirmation before any change."
            ),
            placement="center",
        ),
    ]


def _iam_core() -> List[TourStep]:
    return [
        TourStep(
            key="overview",
            title="Where access is managed",
            body="IAM Admin is the control room for identities, roles, and which apps each person can reach.",
            anchor="main-nav",
            placement="right",
        ),
        TourStep(
            key="users",
            title="Users and their roles",
            body="Users lists every identity and the roles attached to it. Start here to onboard or adjust someone.",
            anchor="nav-users",
            placement="right",
        ),
        TourStep(
            key="roles",
            title="Roles grant access",
            body="Roles are permission bundles. Assigning a role is what grants a user access to an app.",
            anchor="nav-roles",
            placement="right",
        ),
        TourStep(
            key="apps",
            title="Apps and grants",
            body="Apps shows each product in the suite and which roles can reach it.",
            anchor="nav-apps",
            placement="right",
        ),
        TourStep(
            key="connectors",
            title="Outbound integrations",
            body="Connectors configures HTTP / SFTP / webhook integrations the platform calls out to.",
            anchor="nav-connectors",
            placement="right",
        ),
    ]


_APP_CORE = {
    "payguard": _payguard_core,
    "claimguard": _claimguard_core,
    "siu": _siu_core,
    "intake": _intake_core,
    "assistant": _assistant_core,
    "iam": _iam_core,
}

_APP_LABEL = {
    "payguard": "PayGuard",
    "claimguard": "ClaimGuard",
    "siu": "SIU",
    "intake": "the Intake Portal",
    "assistant": "the Assistant",
    "iam": "IAM Admin",
}


# ── Role overlays ─────────────────────────────────────────────────────────────
# Extra steps layered onto the app core for a specific persona. Keyed by
# (app, persona) → steps. Anything not listed uses just the core (analyst/
# specialist baseline).

def _role_overlays(app: str, persona: str) -> List[TourStep]:
    overlays = {
        ("payguard", "supervisor"): [
            TourStep(
                key="approvals",
                title="Cases wait on your sign-off",
                body="High-dollar cases pause in Approvals until a supervisor approves the recovery.",
                anchor="nav-approvals",
                placement="right",
            ),
            TourStep(
                key="provider-risk",
                title="Watch the risky providers",
                body="Provider Risk ranks providers by the ML billing-variance score so you can target reviews.",
                anchor="nav-provider-risk",
                placement="right",
            ),
        ],
        ("payguard", "recoupment_specialist"): [
            TourStep(
                key="delivery",
                title="Your queue starts at delivery",
                body=(
                    "Once a notice goes out, the Delivery Queue and Recovery stage are where you "
                    "record the check / EFT / offset and reconcile against inbound 835s."
                ),
                anchor="nav-delivery-queue",
                placement="right",
            ),
        ],
        ("payguard", "admin"): [
            TourStep(
                key="admin",
                title="Tune the platform",
                body="Admin is where you adjust detector thresholds, manage users, and refresh reference data.",
                anchor="nav-admin",
                placement="right",
            ),
        ],
        ("claimguard", "supervisor"): [
            TourStep(
                key="team",
                title="Keep an eye on the team",
                body="Team Monitor shows each reviewer's queue and throughput at a glance.",
                anchor="nav-team",
                placement="right",
            ),
        ],
        ("claimguard", "admin"): [
            TourStep(
                key="admin",
                title="Tune the platform",
                body="Admin and File Intake let you manage users, rules, and bulk file ingestion.",
                anchor="nav-admin",
                placement="right",
            ),
        ],
    }
    return overlays.get((app, persona), [])


# ── Composer ──────────────────────────────────────────────────────────────────

def build_tour(app: str, role_names: Set[str], accessible_apps: Set[str]) -> Tour:
    """Compose the tailored tour for (app, caller's roles, caller's apps)."""
    if app not in _APP_CORE:
        # Unknown app → a minimal, still-useful intro/outro shell.
        app_label = app
        core: List[TourStep] = []
        persona = "analyst"
    else:
        app_label = _APP_LABEL[app]
        persona = persona_for(app, role_names)
        core = _APP_CORE[app]()

    role_label = ROLE_LABELS.get(persona, persona.replace("_", " ").title())

    # Cross-app links for the outro: apps the caller can reach, minus this one.
    other_apps = [
        link for name, link in _LINKABLE_APPS.items()
        if name in accessible_apps and name != app
    ]

    steps: List[TourStep] = []
    steps += _intro(app_label)
    steps += core
    steps += _role_overlays(app, persona)
    steps += _outro(role_label, other_apps)

    return Tour(app=app, role=persona, role_label=role_label, steps=steps)
