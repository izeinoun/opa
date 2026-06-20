"""Seed RBAC reference data + backfill user_roles from opa_users.role.

Idempotent: if apps/roles already exist with their canonical names, the
seed leaves them alone and only fills in gaps. Safe to re-run.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = datetime.utcnow().isoformat()


# ── Reference data ────────────────────────────────────────────────────────

APPS = [
    ("payguard",   "Post-payment overpayment recovery (the PayGuard UI)"),
    ("claimguard", "Pre-payment claim review (the ClaimGuard UI)"),
    ("siu",        "Special Investigation Unit — fraud, waste & abuse case management and external referrals"),
    ("cob",        "Coordination of Benefits (planned)"),
    ("intake",     "Secure File Intake Portal — drop-folder ingestion for IT/Data teams"),
]

ROLES = [
    ("admin",
     "Platform administrator — all apps, all actions."),
    ("supervisor",
     "Manager-level reviewer — approvals, reassignment, reports across "
     "their assigned apps."),
    ("analyst",
     "Front-line claim reviewer — works the queue, runs AI, drafts letters, "
     "raises cases for supervisor approval."),
    ("specialist",
     "Equivalent of analyst in ClaimGuard's legacy vocabulary — kept as a "
     "distinct role for tenants who use that naming. Same effective access "
     "as analyst on the claimguard app."),
    ("siu_investigator",
     "SIU investigator (alias siu_user) — opens investigations, manages "
     "investigation notes, files law enforcement referrals, and closes "
     "cases back into the PI workflow."),
    ("recoupment_specialist",
     "Recovery operations — records check / EFT / offset, reconciles "
     "against inbound 835s."),
    ("intake",
     "File-intake portal operator (IT/Data team) — may drop files into the "
     "secure intake portal; no access to the analyst apps."),
    ("system",
     "Service / automation account — used by jobs, schedulers, ingest "
     "adapters. Not a human user."),
]

# Role → list of app_names it grants access to.
ROLE_APP_MAP = {
    "admin":                ["payguard", "claimguard", "siu", "cob", "intake"],
    "supervisor":           ["payguard", "claimguard", "siu", "cob"],
    "analyst":              ["payguard", "claimguard"],          # no SIU by default
    "specialist":           ["claimguard"],
    "siu_investigator":     ["siu"],
    "recoupment_specialist": ["payguard"],
    "intake":               ["intake"],                          # portal only
    "system":               ["payguard", "claimguard", "siu", "cob", "intake"],
}


# ── Driver ────────────────────────────────────────────────────────────────

def run(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    try:
        # Insert apps
        app_id_by_name: dict[str, str] = {}
        for name, desc in APPS:
            row = conn.execute(
                "SELECT app_id FROM apps WHERE app_name = ?", (name,)
            ).fetchone()
            if row:
                app_id_by_name[name] = row[0]
                continue
            new_id = str(uuid4())
            conn.execute(
                "INSERT INTO apps (app_id, app_name, description, is_active, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (new_id, name, desc, 1, NOW, NOW),
            )
            app_id_by_name[name] = new_id

        # Insert roles
        role_id_by_name: dict[str, str] = {}
        for name, desc in ROLES:
            row = conn.execute(
                "SELECT role_id FROM roles WHERE role_name = ?", (name,)
            ).fetchone()
            if row:
                role_id_by_name[name] = row[0]
                continue
            new_id = str(uuid4())
            conn.execute(
                "INSERT INTO roles (role_id, role_name, description, "
                "created_at, updated_at) VALUES (?,?,?,?,?)",
                (new_id, name, desc, NOW, NOW),
            )
            role_id_by_name[name] = new_id

        # Insert role_apps
        for role_name, app_names in ROLE_APP_MAP.items():
            role_id = role_id_by_name[role_name]
            for app_name in app_names:
                app_id = app_id_by_name[app_name]
                exists = conn.execute(
                    "SELECT 1 FROM role_apps WHERE role_id=? AND app_id=?",
                    (role_id, app_id),
                ).fetchone()
                if exists:
                    continue
                conn.execute(
                    "INSERT INTO role_apps (role_id, app_id) VALUES (?, ?)",
                    (role_id, app_id),
                )

        # Backfill user_roles from the legacy opa_users.role column.
        # An existing role value that doesn't match a seeded role name is
        # logged and skipped (administrator can add a custom role later).
        users = conn.execute(
            "SELECT user_id, role FROM opa_users WHERE role IS NOT NULL AND role != ''"
        ).fetchall()
        backfilled = 0
        skipped = 0
        for user_id, role_value in users:
            role_id = role_id_by_name.get(role_value)
            if role_id is None:
                print(f"  user_roles: skipped {user_id[:8]} (unknown role={role_value!r})")
                skipped += 1
                continue
            exists = conn.execute(
                "SELECT 1 FROM user_roles WHERE user_id=? AND role_id=?",
                (user_id, role_id),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                "INSERT INTO user_roles (user_id, role_id, granted_at, "
                "granted_by_user_id) VALUES (?, ?, ?, NULL)",
                (user_id, role_id, NOW),
            )
            backfilled += 1

        # Set default_app_id heuristically: analyst/supervisor → payguard,
        # specialist → claimguard, investigator → fwa, admin → payguard.
        DEFAULT_APP_FOR_ROLE = {
            "admin":                 "payguard",
            "supervisor":            "payguard",
            "analyst":               "payguard",
            "specialist":            "claimguard",
            "siu_investigator":      "siu",
            "recoupment_specialist": "payguard",
            "intake":                "intake",
            "system":                "payguard",
        }
        for user_id, role_value in users:
            app_name = DEFAULT_APP_FOR_ROLE.get(role_value)
            if not app_name:
                continue
            app_id = app_id_by_name[app_name]
            conn.execute(
                "UPDATE opa_users SET default_app_id = ? "
                "WHERE user_id = ? AND default_app_id IS NULL",
                (app_id, user_id),
            )

        conn.commit()
        print(f"  RBAC seeded: {len(APPS)} apps, {len(ROLES)} roles, "
              f"{sum(len(v) for v in ROLE_APP_MAP.values())} role→app links")
        print(f"  Backfilled {backfilled} user_roles rows ({skipped} skipped)")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
