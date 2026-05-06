"""Seed 40 members — synchronous sqlite3.

Distribution:
  MA = 16 members (DOB 1940-01-01 – 1958-12-31, age 65+)
  PPO = 16 members (DOB 1964-01-01 – 1994-12-31, working-age)
  Medicaid = 8 members (DOB 1994-01-01 – 2010-12-31, mixed age)

Special cases:
  3 retro-terminated (retro_termination_date set)
  2 deceased (date_of_death set)
"""
from __future__ import annotations

import os
import sqlite3
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2024-01-01T08:00:00"

# (first_name, last_name, dob, lob, coverage_eff, coverage_term, retro_term, dod, member_number)
MEMBERS = [
    # ── Medicare Advantage (16) ────────────────────────────────────────────
    ("Dorothy",   "Hansen",    "1945-03-12", "MA",       "2020-01-01", None,         None,         None,         "MA-000001"),
    ("Harold",    "Simmons",   "1948-07-22", "MA",       "2018-06-01", None,         None,         None,         "MA-000002"),
    ("Evelyn",    "Kowalski",  "1941-11-05", "MA",       "2019-01-01", None,         None,         None,         "MA-000003"),
    ("Walter",    "Pryor",     "1952-04-18", "MA",       "2017-01-01", None,         None,         None,         "MA-000004"),
    ("Ruth",      "Chandler",  "1944-09-30", "MA",       "2021-01-01", None,         None,         None,         "MA-000005"),
    ("Bernard",   "Ostrowski", "1950-02-14", "MA",       "2015-01-01", None,         None,         None,         "MA-000006"),
    ("Mildred",   "Reyes",     "1947-06-07", "MA",       "2022-01-01", None,         None,         None,         "MA-000007"),
    ("Clarence",  "Whitfield", "1943-12-25", "MA",       "2016-01-01", None,         None,         None,         "MA-000008"),
    ("Gertrude",  "Nakamura",  "1955-08-19", "MA",       "2020-08-01", None,         None,         None,         "MA-000009"),
    ("Raymond",   "Benson",    "1949-01-31", "MA",       "2014-01-01", None,         None,         None,         "MA-000010"),
    # Retro-terminated MA members (3)
    ("Agnes",     "Lorenz",    "1946-05-23", "MA",       "2023-01-01", "2023-11-30", "2023-09-30", None,         "MA-000011"),
    ("Franklin",  "Dubois",    "1953-10-10", "MA",       "2022-06-01", "2023-06-30", "2023-03-31", None,         "MA-000012"),
    ("Irene",     "Stafford",  "1940-03-01", "MA",       "2021-01-01", "2023-12-31", "2023-10-01", None,         "MA-000013"),
    # Deceased MA members (2)
    ("Chester",   "Novak",     "1942-07-14", "MA",       "2019-01-01", "2024-03-15", None,         "2024-03-15", "MA-000014"),
    ("Lillian",   "Payne",     "1944-11-28", "MA",       "2018-01-01", "2023-08-20", None,         "2023-08-20", "MA-000015"),
    ("Herman",    "Frazier",   "1951-04-06", "MA",       "2020-01-01", None,         None,         None,         "MA-000016"),
    # ── PPO (16) ───────────────────────────────────────────────────────────
    ("Marcus",    "Jefferson",  "1978-02-17", "PPO",     "2019-03-01", None,         None,         None,         "PPO-000001"),
    ("Natalie",   "Holloway",   "1985-09-05", "PPO",     "2021-01-01", None,         None,         None,         "PPO-000002"),
    ("Derek",     "Carmichael", "1972-06-22", "PPO",     "2017-07-01", None,         None,         None,         "PPO-000003"),
    ("Vanessa",   "Guerrero",   "1990-12-03", "PPO",     "2022-01-01", None,         None,         None,         "PPO-000004"),
    ("Justin",    "Flemming",   "1983-04-11", "PPO",     "2020-04-01", None,         None,         None,         "PPO-000005"),
    ("Stephanie", "Olsen",      "1976-08-29", "PPO",     "2016-01-01", None,         None,         None,         "PPO-000006"),
    ("Aaron",     "Fitzgerald", "1969-01-15", "PPO",     "2018-09-01", None,         None,         None,         "PPO-000007"),
    ("Michelle",  "Blackwood",  "1993-07-04", "PPO",     "2023-01-01", None,         None,         None,         "PPO-000008"),
    ("Tyler",     "Yamamoto",   "1988-03-30", "PPO",     "2021-06-01", None,         None,         None,         "PPO-000009"),
    ("Brianna",   "Castillo",   "1980-10-18", "PPO",     "2019-11-01", None,         None,         None,         "PPO-000010"),
    ("Eric",      "Thornton",   "1974-05-07", "PPO",     "2015-01-01", None,         None,         None,         "PPO-000011"),
    ("Amanda",    "Vickers",    "1991-02-25", "PPO",     "2022-07-01", None,         None,         None,         "PPO-000012"),
    ("Nathan",    "Gould",      "1967-11-13", "PPO",     "2017-01-01", None,         None,         None,         "PPO-000013"),
    ("Jessica",   "Hartman",    "1986-06-16", "PPO",     "2020-10-01", None,         None,         None,         "PPO-000014"),
    ("Patrick",   "Okonkwo",    "1979-09-24", "PPO",     "2018-01-01", None,         None,         None,         "PPO-000015"),
    ("Samantha",  "Ramos",      "1994-01-08", "PPO",     "2023-06-01", None,         None,         None,         "PPO-000016"),
    # ── Medicaid (8) ──────────────────────────────────────────────────────
    ("Destiny",   "Washington", "2001-04-20", "Medicaid","2020-01-01", None,         None,         None,         "MCD-000001"),
    ("Jaylen",    "Crawford",   "1998-11-09", "Medicaid","2019-06-01", None,         None,         None,         "MCD-000002"),
    ("Aaliyah",   "Monroe",     "2005-07-14", "Medicaid","2021-01-01", None,         None,         None,         "MCD-000003"),
    ("Isaiah",    "Tucker",     "1995-03-02", "Medicaid","2018-01-01", None,         None,         None,         "MCD-000004"),
    ("Kylie",     "Perkins",    "2008-09-27", "Medicaid","2022-09-01", None,         None,         None,         "MCD-000005"),
    ("Darius",    "Simms",      "2003-12-11", "Medicaid","2021-12-01", None,         None,         None,         "MCD-000006"),
    ("Tiana",     "Goodwin",    "1997-06-05", "Medicaid","2017-01-01", None,         None,         None,         "MCD-000007"),
    ("Malik",     "Hudson",     "2009-02-19", "Medicaid","2023-02-01", None,         None,         None,         "MCD-000008"),
]


def run(db_path: str = DB_PATH) -> int:
    conn = sqlite3.connect(db_path)
    try:
        if conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]:
            print("  members already seeded — skipping")
            return 0

        for (first, last, dob, lob, cov_eff, cov_term, retro_term, dod, mnum) in MEMBERS:
            conn.execute(
                "INSERT INTO members "
                "(member_id, member_number, first_name, last_name, date_of_birth, "
                "date_of_death, lob, coverage_effective_date, coverage_termination_date, "
                "retro_termination_date, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (str(uuid4()), mnum, first, last, dob, dod, lob, cov_eff, cov_term, retro_term, NOW, NOW),
            )

        conn.commit()
        print(f"  Inserted {len(MEMBERS)} members")
        return len(MEMBERS)
    finally:
        conn.close()


if __name__ == "__main__":
    run()
