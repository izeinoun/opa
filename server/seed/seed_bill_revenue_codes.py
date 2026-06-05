"""Seed bill type codes and revenue codes for DET-10."""
from __future__ import annotations

import os
import sqlite3
from uuid import uuid4

DB_PATH = os.getenv("DB_PATH", "./opa.db")
NOW = "2024-01-01T08:00:00"
CMS_UB = "https://www.cms.gov/medicare/billing/electronicbillingediforms/ub-04"

# (code, description, facility_type, bill_classification, frequency)
BILL_TYPE_CODES = [
    ("111", "Inpatient Hospital — Admit through Discharge",       "hospital",    "inpatient",  "admit_discharge"),
    ("112", "Inpatient Hospital — Interim (First)",               "hospital",    "inpatient",  "interim_first"),
    ("113", "Inpatient Hospital — Interim (Continuing)",          "hospital",    "inpatient",  "interim_continuing"),
    ("114", "Inpatient Hospital — Interim (Last)",                "hospital",    "inpatient",  "interim_last"),
    ("117", "Inpatient Hospital — Replacement",                   "hospital",    "inpatient",  "replacement"),
    ("131", "Outpatient Hospital — Admit through Discharge",      "hospital",    "outpatient", "admit_discharge"),
    ("132", "Outpatient Hospital — Interim (First)",              "hospital",    "outpatient", "interim_first"),
    ("134", "Outpatient Hospital — Interim (Last)",               "hospital",    "outpatient", "interim_last"),
    ("137", "Outpatient Hospital — Replacement",                  "hospital",    "outpatient", "replacement"),
    ("141", "Other Hospital — Admit through Discharge",           "hospital",    "other",      "admit_discharge"),
    ("211", "Skilled Nursing Facility — Inpatient Admit through Discharge", "snf", "inpatient", "admit_discharge"),
    ("212", "Skilled Nursing Facility — Interim (First)",         "snf",         "inpatient",  "interim_first"),
    ("213", "Skilled Nursing Facility — Interim (Continuing)",    "snf",         "inpatient",  "interim_continuing"),
    ("214", "Skilled Nursing Facility — Interim (Last)",          "snf",         "inpatient",  "interim_last"),
    ("321", "Home Health — Admit through Discharge",              "home_health", "outpatient", "admit_discharge"),
    ("322", "Home Health — Interim (First)",                      "home_health", "outpatient", "interim_first"),
    ("324", "Home Health — Interim (Last)",                       "home_health", "outpatient", "interim_last"),
    ("711", "Rural Health Clinic — Admit through Discharge",      "clinic",      "outpatient", "admit_discharge"),
    ("831", "Ambulatory Surgical Center — Admit through Discharge","asc",        "outpatient", "admit_discharge"),
]

# (code, description, category, typical_setting, requires_units)
REVENUE_CODES = [
    # Room & Board
    ("0100", "All-Inclusive Room and Board",              "room_board",  "inpatient", True),
    ("0110", "Room & Board — Private (Medical/General)",  "room_board",  "inpatient", True),
    ("0120", "Room & Board — Semi-Private (2 Beds)",      "room_board",  "inpatient", True),
    ("0130", "Room & Board — Semi-Private (3–4 Beds)",    "room_board",  "inpatient", True),
    ("0140", "Room & Board — Private (Deluxe)",           "room_board",  "inpatient", True),
    ("0160", "Room & Board — Other",                      "room_board",  "inpatient", True),

    # ICU / Special Care
    ("0200", "Intensive Care Unit (ICU) — General",       "special_care","inpatient", True),
    ("0201", "Intensive Care Unit — Surgical",            "special_care","inpatient", True),
    ("0202", "Intensive Care Unit — Medical",             "special_care","inpatient", True),
    ("0206", "Intensive Care Unit — Intermediate",        "special_care","inpatient", True),
    ("0210", "Coronary Care Unit (CCU)",                  "special_care","inpatient", True),

    # Ancillary
    ("0250", "Pharmacy — General",                        "pharmacy",    "both",      True),
    ("0251", "Pharmacy — Generic Drugs",                  "pharmacy",    "both",      True),
    ("0252", "Pharmacy — Non-Generic Drugs",              "pharmacy",    "both",      True),
    ("0260", "IV Therapy",                                "ancillary",   "both",      True),
    ("0270", "Medical/Surgical Supplies — General",       "ancillary",   "both",      True),
    ("0272", "Sterile Supplies",                          "ancillary",   "both",      True),
    ("0278", "Other Implants",                            "ancillary",   "both",      True),

    # Laboratory
    ("0300", "Laboratory — General",                      "laboratory",  "both",      True),
    ("0301", "Laboratory — Chemistry",                    "laboratory",  "both",      True),
    ("0302", "Laboratory — Immunology",                   "laboratory",  "both",      True),
    ("0303", "Laboratory — Renal Patient",                "laboratory",  "inpatient", True),
    ("0305", "Laboratory — Hematology",                   "laboratory",  "both",      True),
    ("0307", "Laboratory — Bacteriology / Microbiology",  "laboratory",  "both",      True),
    ("0310", "Laboratory — Pathology",                    "laboratory",  "both",      True),
    ("0311", "Laboratory — Cytology",                     "laboratory",  "both",      True),
    ("0312", "Laboratory — Histology",                    "laboratory",  "both",      True),

    # Radiology
    ("0320", "Radiology — Diagnostic",                    "radiology",   "both",      True),
    ("0321", "Radiology — Chest X-Ray",                   "radiology",   "both",      True),
    ("0322", "Radiology — Therapeutic",                   "radiology",   "both",      True),
    ("0324", "Radiology — Diagnostic — Ultrasound",       "radiology",   "both",      True),
    ("0330", "Radiology — CT Scan",                       "radiology",   "both",      True),
    ("0340", "Nuclear Medicine — General",                "radiology",   "both",      True),
    ("0350", "MRI — General",                             "radiology",   "both",      True),

    # OR / Procedures
    ("0360", "Operating Room Services",                   "or_services", "both",      True),
    ("0361", "Operating Room — Minor",                    "or_services", "both",      True),
    ("0370", "Anesthesia",                                "anesthesia",  "both",      True),
    ("0380", "Blood",                                     "ancillary",   "both",      True),
    ("0381", "Packed Red Cells",                          "ancillary",   "both",      True),

    # Therapy
    ("0410", "Respiratory Services — General",            "therapy",     "both",      True),
    ("0420", "Physical Therapy — General",                "therapy",     "both",      True),
    ("0421", "Physical Therapy — Visit",                  "therapy",     "both",      True),
    ("0430", "Occupational Therapy — General",            "therapy",     "both",      True),
    ("0431", "Occupational Therapy — Visit",              "therapy",     "both",      True),
    ("0440", "Speech Pathology — General",                "therapy",     "both",      True),
    ("0480", "Cardiology — General",                      "ancillary",   "both",      True),
    ("0481", "Cardiac Catheterization Lab",               "ancillary",   "both",      True),

    # Emergency / Observation
    ("0450", "Emergency Room — General",                  "emergency",   "outpatient",True),
    ("0451", "Emergency Room — EMTALA",                   "emergency",   "outpatient",True),
    ("0460", "Pulmonary Function",                        "ancillary",   "both",      True),
    ("0490", "Ambulatory Surgical Care",                  "or_services", "outpatient",True),
    ("0762", "Observation Room",                          "observation", "outpatient",True),

    # Other ancillary
    ("0510", "Clinic — General",                          "clinic",      "outpatient",True),
    ("0520", "Free-Standing Clinic",                      "clinic",      "outpatient",True),
    ("0540", "Ambulance",                                 "transport",   "both",      True),
    ("0630", "Drugs Requiring Detailed Coding (Take Home)","pharmacy",   "both",      True),
    ("0710", "Recovery Room",                             "ancillary",   "both",      True),
    ("0720", "Labor Room / Delivery",                     "ancillary",   "inpatient", True),
    ("0730", "EKG / ECG",                                 "ancillary",   "both",      True),
    ("0740", "EEG",                                       "ancillary",   "both",      True),
    ("0750", "Gastro-Intestinal Services",                "ancillary",   "both",      True),
    ("0800", "Inpatient Renal Dialysis — General",        "dialysis",    "inpatient", True),
    ("0820", "Hemodialysis — Outpatient",                 "dialysis",    "outpatient",True),
    ("0900", "Psychiatric / Psychological — General",     "behavioral",  "both",      True),
    ("0901", "Psychiatric — Room and Board",              "behavioral",  "inpatient", True),
    ("0940", "Other Therapeutic Services",                "ancillary",   "both",      True),
    ("0960", "Professional Fees — General",               "professional","both",      False),
    ("0961", "Professional Fees — Psychiatric",           "professional","both",      False),
]


def run(db_path: str = DB_PATH) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # Bill type codes
    existing_btc = {r[0] for r in cur.execute("SELECT code FROM bill_type_codes")}
    btc_rows = [
        (str(uuid4()), code, desc, fac, cls_, freq, 1, "CMS UB-04 Billing Manual", NOW, NOW)
        for (code, desc, fac, cls_, freq) in BILL_TYPE_CODES
        if code not in existing_btc
    ]
    if btc_rows:
        cur.executemany(
            "INSERT INTO bill_type_codes "
            "(bill_type_code_id, code, description, facility_type, bill_classification, frequency, "
            " is_active, source_authority, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            btc_rows,
        )

    # Revenue codes
    existing_rc = {r[0] for r in cur.execute("SELECT code FROM revenue_codes")}
    rc_rows = [
        (str(uuid4()), code, desc, cat, setting, 1 if req_units else 0, 1, CMS_UB, NOW, NOW)
        for (code, desc, cat, setting, req_units) in REVENUE_CODES
        if code not in existing_rc
    ]
    if rc_rows:
        cur.executemany(
            "INSERT INTO revenue_codes "
            "(revenue_code_id, code, description, category, typical_setting, "
            " requires_units, is_active, source_authority, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            rc_rows,
        )

    con.commit()
    con.close()
    print(f"  bill_type_codes: {len(btc_rows)} inserted  revenue_codes: {len(rc_rows)} inserted")


if __name__ == "__main__":
    run()
