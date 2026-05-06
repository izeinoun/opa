"""Seed OPA users — synchronous sqlite3."""
from __future__ import annotations

import os
import sqlite3
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2024-01-01T08:00:00"

USERS = [
    ("ana.chen",      "Ana Chen",          "ana.chen@opa.internal",      "analyst"),
    ("james.park",    "James Park",        "james.park@opa.internal",    "analyst"),
    ("priya.shah",    "Priya Shah",        "priya.shah@opa.internal",    "analyst"),
    ("tom.rivera",    "Tom Rivera",        "tom.rivera@opa.internal",    "analyst"),
    ("lisa.nguyen",   "Lisa Nguyen",       "lisa.nguyen@opa.internal",   "analyst"),
    ("marcus.bell",   "Marcus Bell",       "marcus.bell@opa.internal",   "analyst"),
    ("sarah.kim",     "Sarah Kim",         "sarah.kim@opa.internal",     "supervisor"),
    ("david.osei",    "David Osei",        "david.osei@opa.internal",    "supervisor"),
    ("rachel.burns",  "Rachel Burns",      "rachel.burns@opa.internal",  "admin"),
    ("system.bot",    "System Bot",        "system@opa.internal",        "system"),
]


def run(db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM opa_users").fetchone()[0]
        if count:
            print(f"  opa_users already has {count} rows — skipping")
            return 0

        rows = []
        for username, full_name, email, role in USERS:
            rows.append((
                str(uuid4()), username, full_name, email, role, 1, NOW, NOW,
            ))

        conn.executemany(
            "INSERT INTO opa_users "
            "(user_id, username, full_name, email, role, is_active, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        print(f"  Inserted {len(rows)} users")
        return len(rows)
    finally:
        conn.close()


if __name__ == "__main__":
    run()
