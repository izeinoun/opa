"""Generate realistic HMO contract PDF with carve-outs for demo purposes.

This contract includes:
- Behavioral Health Carve-Out (pre-auth required, separate network)
- Pharmacy Carve-Out (formulary restrictions, step therapy)
- DME Carve-Out (limited vendors, rental/purchase rules)
- Emergency services rules
- Medical necessity requirements
- Complex authorization requirements

The PDF is generated with embedded text that can be extracted/analyzed by LLMs.
"""
from fpdf import FPDF
from datetime import datetime
from pathlib import Path

CONTRACT_TEXT = """
HEALTH MAINTENANCE ORGANIZATION (HMO) MEMBER SERVICES CONTRACT
Premium Plus HMO Plan 2024-2025

EFFECTIVE DATE: January 1, 2024
RENEWAL DATE: December 31, 2024

═══════════════════════════════════════════════════════════════════════════════

TABLE OF CONTENTS

1. PLAN OVERVIEW AND KEY TERMS
2. MEMBER ELIGIBILITY AND ENROLLMENT
3. COVERED SERVICES AND BENEFITS
4. BEHAVIORAL HEALTH CARVE-OUT (MENTAL HEALTH & SUBSTANCE ABUSE)
5. PHARMACY CARVE-OUT AND DRUG FORMULARY
6. DURABLE MEDICAL EQUIPMENT (DME) CARVE-OUT
7. EMERGENCY AND URGENT CARE SERVICES
8. PRIOR AUTHORIZATION AND MEDICAL NECESSITY
9. OUT-OF-NETWORK COVERAGE LIMITATIONS
10. CLAIMS SUBMISSION AND PAYMENT
11. MEDICAL POLICIES AND CLINICAL GUIDELINES
12. EXCLUSIONS AND LIMITATIONS
13. MEMBER RIGHTS AND APPEALS
14. COMPLIANCE AND FRAUD PREVENTION

═══════════════════════════════════════════════════════════════════════════════

1. PLAN OVERVIEW AND KEY TERMS

1.1 PLAN STRUCTURE
Premium Plus HMO is a Health Maintenance Organization (HMO) designed to provide
coordinated care through a network of healthcare providers. Members must select a
Primary Care Physician (PCP) who authorizes all specialty referrals and coordinates care.

1.2 NETWORK REQUIREMENTS
- Primary Care: Must use in-network PCP
- Specialists: Must obtain referral from PCP except in emergencies
- Behavioral Health: Separate carved-out network (see Section 4)
- Pharmacy: Separate carved-out network (see Section 5)
- DME: Limited to approved vendors (see Section 6)

1.3 COVERED SERVICES
All services listed in Section 3 when provided by in-network providers.
Out-of-network services are NOT covered except emergency services as defined in Section 7.

1.4 MEMBER COST-SHARING
- Copay (Office Visit): $25/visit
- Copay (Preventive): $0
- Copay (Specialist): $40/visit
- Copay (Urgent Care): $50/visit
- Copay (Emergency Room): $250 (waived if admitted)
- Deductible: $500/year (per member)
- Out-of-Pocket Maximum: $3,500/year (individual)

═══════════════════════════════════════════════════════════════════════════════

2. MEMBER ELIGIBILITY AND ENROLLMENT

2.1 ELIGIBLE POPULATIONS
- Employees of contracted employers
- Medicare Advantage members (age 65+)
- Medicaid members (where applicable)
- Family members (spouse, children to age 26)

2.2 ENROLLMENT PERIODS
- Initial: Within 30 days of eligibility
- Open: November 1 - December 31 annually
- Special: Qualifying life events (marriage, birth, loss of coverage)

2.3 EFFECTIVE DATE
Coverage begins the first day of the month following approval.
Pre-existing condition exclusions prohibited.

═══════════════════════════════════════════════════════════════════════════════

3. COVERED SERVICES AND BENEFITS

3.1 PREVENTIVE CARE (COVERED AT NO COST)
- Annual physical examination
- Age-appropriate cancer screenings (breast, prostate, colon)
- Immunizations per ACIP recommendations
- Blood pressure screening
- Cholesterol screening
- Diabetes screening
- Osteoporosis screening (age 65+)
- Depression screening

3.2 OFFICE VISITS AND PRIMARY CARE
- Primary care physician visits: $25 copay
- Nurse advice line: $0
- Telehealth visits: $15 copay
- Urgent care (in-network): $50 copay
- Emergency room: $250 (waived if admitted)

3.3 HOSPITALIZATION
- Inpatient hospital stays: Covered at 100% after deductible
- Maternity care: Covered without separate authorization
- Mental health inpatient: Covered via behavioral health carve-out
- Surgical procedures: Covered when medically necessary

3.4 SPECIALIST CARE
- Requires referral from PCP (except behavioral health)
- Copay: $40/visit
- Surgical procedures: Requires prior authorization (see Section 8)
- Imaging: Requires prior authorization for advanced imaging

3.5 LABORATORY AND DIAGNOSTIC TESTING
- Routine lab work: $0 copay (covered at 100%)
- Advanced imaging (MRI, CT): Prior authorization required
- Nuclear medicine: Prior authorization required
- Ultrasound: Covered at 100% after deductible

3.6 REHABILITATION SERVICES
- Physical therapy: 30 visits/year, $25 copay per visit
- Occupational therapy: 30 visits/year, $25 copay per visit
- Speech therapy: 30 visits/year, $25 copay per visit
- Requires medical necessity certification

3.7 PHARMACY BENEFITS
See Section 5 (Pharmacy Carve-Out) for complete pharmacy coverage details.
Copay structure: Generic $10, Brand formulary $25, Non-formulary $50

═══════════════════════════════════════════════════════════════════════════════

4. BEHAVIORAL HEALTH CARVE-OUT (MENTAL HEALTH & SUBSTANCE ABUSE)

4.1 CARVE-OUT STRUCTURE
Behavioral health services are carved out to "Acme Behavioral Health Network"
and managed separately from primary medical services. Members must use in-network
behavioral health providers.

4.2 COVERED BEHAVIORAL HEALTH SERVICES
- Outpatient psychiatry: Covered, $25 copay
- Outpatient psychotherapy: Covered, $25 copay
- Psychiatric medication management: Covered, $25 copay
- Partial hospitalization program (PHP): Covered, requires pre-auth
- Intensive outpatient program (IOP): Covered, requires pre-auth
- Inpatient psychiatric hospitalization: Covered, requires pre-auth
- Residential treatment facilities: Covered, requires medical necessity review
- Crisis intervention services: Covered 24/7, $0 copay
- Substance abuse treatment: Covered per medical necessity
- Detoxification programs: Covered, requires pre-auth
- Medication-assisted treatment (MAT): Covered with specialist authorization

4.3 AUTHORIZATION REQUIREMENTS FOR BEHAVIORAL HEALTH

OUTPATIENT THERAPY:
- First 20 visits per year: Covered without prior authorization
- Visits 21-40: Requires provider certification of medical necessity
- Visits 41+: Requires authorization review, renewal every 4 weeks
- Authorization criteria: Specific diagnosis codes (F32-F39, F41-F42, F43-F48)

INPATIENT PSYCHIATRIC:
- All inpatient admissions: Require pre-authorization before admission
- Certification required: Medical necessity and least restrictive setting
- Concurrent review: Required for stays exceeding 5 days
- Discharge planning: Required to coordinate post-discharge care

PHP/IOP:
- All admissions: Require prior authorization
- Medical necessity: Documented by treating psychiatrist
- Utilization review: Required every 14 days

4.4 BEHAVIORAL HEALTH NETWORK
Members must use network providers. Out-of-network behavioral health services
are NOT covered except in emergency circumstances.

Approved behavioral health providers can be found at: www.acmebehavioralhealth.com

4.5 CARVE-OUT CONTACT INFORMATION
Acme Behavioral Health Network
Prior Authorization Line: 1-800-MENTAL-1
Provider Line: 1-800-BEHAV-NET
Hours: 24/7

4.6 BEHAVIORAL HEALTH EXCLUSIONS
- Non-diagnostic services (counseling for social adjustment without medical diagnosis)
- Marital or relationship counseling
- Career counseling
- Services not related to diagnosable mental health condition
- Court-ordered evaluations (unless for commitment proceedings)

═══════════════════════════════════════════════════════════════════════════════

5. PHARMACY CARVE-OUT AND DRUG FORMULARY

5.1 CARVE-OUT STRUCTURE
Pharmacy benefits are carved out to "Express Pharmacy Network" and managed
separately. Members must use network pharmacies and must follow formulary
restrictions and prior authorization requirements.

5.2 PHARMACY COPAY STRUCTURE
- Generic drugs: $10
- Formulary brand-name drugs: $25
- Non-formulary drugs: $50 + any cost difference
- Maintenance medications (90-day supply): $20, $40, $75

5.3 FORMULARY REQUIREMENTS
All prescription medications must be on the Express Pharmacy Formulary
(see www.expresspharmacy.net for current formulary).

EXCEPTIONS TO FORMULARY:
- Non-formulary drugs may be covered if:
  * Prior authorization is obtained from Express Pharmacy
  * Prescriber documents medical necessity
  * All formulary alternatives have been tried and failed
  * Patient has no therapeutic alternative available

5.4 STEP THERAPY REQUIREMENTS
Certain medications require step therapy (trying cheaper/safer alternatives first):

ANTIDEPRESSANTS:
- Step 1: Generic SSRI (citalopram, sertraline, fluoxetine)
- Step 2: Other generic antidepressants
- Step 3: Brand-name or non-formulary antidepressants with prior auth

ANTIHYPERTENSIVES:
- Step 1: Generic lisinopril or hydrochlorothiazide
- Step 2: Other generic antihypertensives
- Step 3: Brand-name with prior auth and documented treatment failure

STATINS:
- Step 1: Generic atorvastatin or simvastatin
- Step 2: Other generic statins
- Step 3: Brand-name with prior auth

BIOLOGICS (Specialty Drugs):
- All biologic medications require prior authorization
- Medical necessity review
- Documented failure of standard therapies required

5.5 PRIOR AUTHORIZATION PROCESS
- Request submitted by pharmacy or prescriber
- Reviewed within 24 hours (expedited) or 5 business days (standard)
- Urgent requests: Same-day review available for acute conditions
- Appeals: Member or prescriber may appeal denial

5.6 PHARMACY NETWORK
Members must use in-network pharmacies:
- CVS/Pharmacy locations (all stores)
- Walgreens locations (participating only)
- Walmart Pharmacy locations (all stores)
- Mail-order pharmacy (Express Mail Pharmacy, 90-day supply recommended)

Express Pharmacy Network: 1-800-EXPRESS-RX
Hours: 24/7

5.7 PHARMACY EXCLUSIONS
- Over-the-counter medications
- Cosmetic drugs
- Experimental drugs (not FDA-approved)
- Drugs for erectile dysfunction (covered only for diabetic neuropathy cause)
- Weight loss medications (non-surgical)
- Immunizations (covered under medical benefits)

═══════════════════════════════════════════════════════════════════════════════

6. DURABLE MEDICAL EQUIPMENT (DME) CARVE-OUT

6.1 CARVE-OUT STRUCTURE
DME is carved out to "Optimal Medical Supply Company" and must be obtained
from approved vendors only. Prior authorization required for all DME.

6.2 COVERED DME ITEMS
- Wheelchairs and mobility devices
- Walkers, canes, crutches
- Hospital beds
- Ventilators and respiratory equipment
- Oxygen equipment and supplies
- CPAP/BiPAP machines and masks
- Diabetic supplies (meters, strips, lancets)
- Compression stockings
- Back/neck braces and orthotics
- Ostomy supplies

6.3 RENTAL vs. PURCHASE RULES

RENTAL ITEMS (covered for limited period):
- Wheelchairs: Rent for 6 months, then must purchase
- Hospital beds: Rent for 6 months, then must purchase
- Walkers: Rent for 3 months, then must purchase
- Crutches: Rent for 2 months, then must purchase

PURCHASE ITEMS (one-time or annual):
- Diabetic supplies: Replaced quarterly
- Ostomy supplies: Up to $1,200/year
- Compression stockings: 2 pairs annually
- Orthotics/braces: 1 per item per year

EXCEPTION: Renal patients requiring equipment for home dialysis may rent
indefinitely with authorization.

6.4 PRIOR AUTHORIZATION REQUIREMENTS
ALL DME requires prior authorization:
- Prescriber must submit order with medical justification
- Diagnosis and functional impairment required
- Specifications of item (model, features)
- Quantity and duration
- Authorization valid for 90 days from approval

6.5 APPROVED DME VENDORS
Optimal Medical Supply Company (Exclusive Network):
- Main: 1-800-OPTIMAL-1
- Phone orders: Same-day processing
- Delivery: 2-3 business days
- Emergency: 24-hour availability

No other vendors are in-network. Out-of-network DME is NOT covered.

6.6 DME COVERAGE LIMITS
- Diabetic test strips: 100 per month (maximum)
- Lancets: 100 per month (maximum)
- Syringes: Covered under pharmacy carve-out
- Catheter supplies: Covered only if medically necessary (spinal cord injury, etc.)

6.7 DME DENIALS AND APPEALS
Common denial reasons:
- Insufficient medical documentation
- Item not on approved list
- Frequency limits exceeded
- Prior authorization expired
- Non-network vendor used

Appeals available within 30 days of denial notice.

═══════════════════════════════════════════════════════════════════════════════

7. EMERGENCY AND URGENT CARE SERVICES

7.1 EMERGENCY SERVICES DEFINITION
An "emergency" is a medical condition with acute symptoms of sufficient severity
(including mental health crises) that a reasonable person would seek immediate care:

Examples:
- Acute chest pain
- Difficulty breathing
- Loss of consciousness
- Severe trauma/injury
- Acute abdominal pain
- Acute psychiatric symptoms (suicidal/homicidal ideation)
- Stroke symptoms

7.2 EMERGENCY ROOM COVERAGE
- Copay: $250 (waived if admitted to hospital)
- Deductible: Not applied to emergency services
- In-network emergency rooms: Covered 100% after copay
- Out-of-network emergency rooms: Covered 100% after copay (ONLY if true emergency)

7.3 URGENT CARE COVERAGE
- Copay: $50/visit
- Must be in-network urgent care center
- Includes sprains, minor cuts, minor burns, fever, respiratory infections
- Does NOT include routine office visits or preventive care

7.4 OUT-OF-NETWORK EMERGENCY SERVICES
Out-of-network emergency rooms ARE covered for true emergencies ONLY when:
- Member was not able to reach in-network emergency room
- Life-threatening condition requiring nearest emergency care
- Member provides documentation within 30 days of service

Stabilization services at out-of-network ER are covered; transfer to in-network
hospital is required when medically appropriate.

7.5 EMERGENCY BEHAVIORAL HEALTH
- Crisis hotline: $0, available 24/7
- Emergency psychiatric services: Covered via behavioral health carve-out
- Inpatient psychiatric admission: Covered, requires authorization within 24 hours
- Emergency medications: Covered under pharmacy carve-out

═══════════════════════════════════════════════════════════════════════════════

8. PRIOR AUTHORIZATION AND MEDICAL NECESSITY

8.1 SERVICES REQUIRING PRIOR AUTHORIZATION
- Elective surgeries
- Advanced imaging (MRI, CT, nuclear medicine)
- Mental health inpatient and intensive services
- Specialty pharmaceutical (biologic drugs)
- Physical/occupational/speech therapy beyond 10 visits
- Durable medical equipment
- High-cost diagnostic procedures
- Out-of-network services
- Experimental treatments

8.2 MEDICAL NECESSITY CRITERIA
Services must meet ALL of the following:
- Appropriate for member's diagnosis
- Most cost-effective treatment option available
- Based on evidence-based clinical guidelines
- Consistent with peer-reviewed clinical literature
- Prescribed by qualified provider within scope of practice
- Not primarily for convenience or comfort

8.3 PRIOR AUTHORIZATION PROCESS
- Submitted by provider or member
- Initial review within 5 business days (standard)
- Expedited review (24 hours) for urgent conditions
- Denial includes specific reason and appeal rights
- Authorization valid for 90 days from approval date

8.4 AUTHORIZATION DENIALS
If prior authorization is denied:
- Written notification within 5 business days
- Specific clinical reason for denial
- Appeal rights clearly explained
- Member and provider notified simultaneously

═══════════════════════════════════════════════════════════════════════════════

9. OUT-OF-NETWORK COVERAGE LIMITATIONS

9.1 OUT-OF-NETWORK COVERAGE POLICY
Premium Plus HMO does NOT cover out-of-network services except:
1. Emergency services (Section 7)
2. Pre-authorized specialty care when no in-network alternative exists
3. Behavioral health emergency crisis services
4. Authorized urgent care when in-network unavailable

9.2 REFERRAL OUT-OF-NETWORK
PCP may refer to out-of-network specialist if:
- No in-network specialist available for condition
- Member requests out-of-network with documented reason
- Request approved in writing by plan medical director
- Member signs acknowledgment of higher out-of-pocket costs

9.3 MEMBER LIABILITY FOR OUT-OF-NETWORK
- Member responsible for any balance billing
- Plan pays no more than in-network rate
- Member may owe difference between out-of-network charge and in-network rate
- Deductible and copay still apply

═══════════════════════════════════════════════════════════════════════════════

10. CLAIMS SUBMISSION AND PAYMENT

10.1 CLAIMS PROCEDURES
- In-network providers: File claims directly (no member responsibility)
- Out-of-network providers: Member may need to file claims
- Claims deadline: 90 days from service date
- Processing time: 20 business days standard, 5 business days expedited

10.2 CLAIM DENIALS
Common reasons for denial:
- Service not covered under plan
- Prior authorization not obtained
- Service not medically necessary
- Claim submitted after 90-day deadline
- Duplicate claim or payment already made
- Out-of-network service (non-emergency)
- Carve-out violation (behavioral health, pharmacy, DME)

10.3 APPEAL PROCESS
- File appeal within 30 days of denial notice
- Include supporting medical documentation
- First-level appeal: Independent clinical review
- Second-level appeal: Medical director review
- Expedited appeal available for urgent claims

10.4 NETWORK PROVIDER PAYMENT TERMS
- Claims adjudicated within 20 days
- Payment within 30 days of adjudication
- Electronic claims preferred; paper claims accepted
- Claims submitted to: claims@premiumplushmo.com

═══════════════════════════════════════════════════════════════════════════════

11. MEDICAL POLICIES AND CLINICAL GUIDELINES

11.1 MEDICAL NECESSITY POLICIES
The plan uses evidence-based clinical guidelines for determining medical
necessity, including:
- Cochrane systematic reviews
- USPSTF guidelines
- Clinical speciality society guidelines
- FDA approvals and package inserts
- State/federal regulatory requirements

11.2 COVERAGE LIMITATIONS BY DIAGNOSIS
Certain diagnoses have specific coverage limitations:

DIABETES:
- HbA1c monitoring: Every 3 months for uncontrolled, every 6 months for controlled
- Diabetic eye exams: Annual
- Foot care: 2 visits/year for established neuropathy
- Continuous glucose monitors: Covered with authorization for insulin-dependent

HYPERTENSION:
- Home blood pressure monitoring: Covered device and training
- Blood pressure checks: Covered as office visit or telehealth
- Medication management: Covered per pharmacy formulary

CHRONIC PAIN:
- Opioid therapy: Requires morphine equivalent dose (MED) assessment
- MED limit: 90 mg/day requires authorization
- MED limit: 120 mg/day requires pain management specialist co-management
- Physical therapy preferred over opioid escalation

CANCER:
- Chemotherapy: Covered when evidence-based per NCCN guidelines
- Radiation therapy: Covered when evidence-based per NCCN guidelines
- Immunotherapy: Covered with prior authorization
- Clinical trials: Covered if life-threatening cancer and no FDA-approved alternative

11.3 INVESTIGATIONAL/EXPERIMENTAL SERVICES
Experimental treatments are NOT covered unless:
- Part of approved clinical trial
- FDA investigational new drug (IND) application
- Approved by medical director and ethics committee
- Member provides informed consent

═══════════════════════════════════════════════════════════════════════════════

12. EXCLUSIONS AND LIMITATIONS

12.1 EXCLUDED SERVICES
The following services are NOT covered:
- Cosmetic procedures (including cosmetic dentistry)
- Weight loss surgery (except for diabetes management)
- Dietary supplements and vitamins
- Over-the-counter medications
- Non-FDA approved medications
- Services outside scope of medical practice
- Services provided by non-licensed providers
- Services for which member is not charged (indigent care)

12.2 EXCLUDED PROVIDERS
Services by the following are NOT covered:
- Unlicensed practitioners
- Providers without appropriate credentials
- Excluded providers (OIG LEIE list)
- Providers with active fraud investigations
- Family members (except in emergency)

12.3 FREQUENCY LIMITATIONS
- Office visits: Unlimited (reasonable frequency)
- Physical therapy: 30 visits/year (extendable with authorization)
- Mental health outpatient: 40 visits/year (extendable with authorization)
- Lab testing: Reasonable frequency per clinical guidelines

12.4 AGE/GENDER LIMITATIONS
- Viagra and similar drugs: Covered only if documented cause (diabetes, spinal cord injury)
- Hormone replacement therapy (HRT): Limited to 5 years, age 45-65
- Preventive services: Age-appropriate per USPSTF recommendations

═══════════════════════════════════════════════════════════════════════════════

13. MEMBER RIGHTS AND APPEALS

13.1 MEMBER RIGHTS
- Right to choose in-network PCP
- Right to request specialists (via PCP referral)
- Right to emergency care
- Right to see medical records
- Right to file appeal within 30 days
- Right to external appeal review
- Right to know insurance company appeal decisions within 30 days
- Right to receive explanations of benefits (EOB)

13.2 APPEAL PROCEDURE
Level 1: Plan-level appeal
- File within 30 days of adverse determination
- Include medical records supporting appeal
- Plan responds within 30 days
- Independent clinical reviewer assigned

Level 2: External appeal
- File if Level 1 appeal denied
- Independent external review organization conducts review
- Decision within 30 days
- Member not responsible for review costs

13.3 EMERGENCY APPEAL
- Available for urgent conditions
- Oral request accepted (document in writing within 24 hours)
- Decision within 24 hours for expedited appeals
- Coverage continues during appeal for urgent conditions

═══════════════════════════════════════════════════════════════════════════════

14. COMPLIANCE AND FRAUD PREVENTION

14.1 FRAUD PREVENTION MEASURES
The plan has procedures to detect and prevent fraud:
- Claims pattern analysis
- Prior authorization verification
- Network provider audits
- Member complaint investigation
- Coordination of benefits review

14.2 PROVIDER CREDENTIALING
All in-network providers must meet:
- Current licensure and DEA registration
- No OIG LEIE exclusion
- Clean medical liability history
- Malpractice insurance verification
- Educational credential verification
- Initial credentialing: 60 days
- Recredentialing: Every 3 years

14.3 MEMBER REPORTING
Members may report suspected fraud:
- Call: 1-800-REPORT-FRAUD
- Online: www.premiumplushmo.com/report-fraud
- Mail: Compliance Department, Premium Plus HMO, PO Box 12345
- Confidential reporting available

═══════════════════════════════════════════════════════════════════════════════

AGREEMENT

By enrolling in Premium Plus HMO, member acknowledges:
1. Receipt and review of this contract
2. Understanding of covered services and cost-sharing
3. Understanding of carve-out services and separate networks
4. Agreement to follow utilization management requirements
5. Agreement to use in-network providers except emergencies
6. Understanding of prior authorization requirements
7. Agreement to appeal deadlines and procedures

Member Signature: _________________________ Date: ______________
Representative Signature: ___________________ Date: ______________

Effective Date: January 1, 2024
Renewal Date: December 31, 2024

═══════════════════════════════════════════════════════════════════════════════

This contract is subject to applicable state and federal insurance regulations.
For questions, contact Premium Plus HMO Member Services at 1-800-PREMIUM-1.

Hours: Monday-Friday 8am-8pm, Saturday 9am-2pm Eastern Time
Website: www.premiumplushmo.com
"""


def generate_hmo_contract_pdf(output_path: str) -> tuple[str, str]:
    """Generate HMO contract PDF with embedded text for LLM analysis.

    Returns:
        Tuple of (pdf_path, contract_text)
    """
    pdf = FPDF(orientation='P', unit='mm', format='Letter')
    pdf.add_page()

    # Set up fonts
    pdf.set_font('Helvetica', '', 9)

    # Title
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, 'PREMIUM PLUS HMO', ln=True, align='C')
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 8, 'Member Services Contract 2024-2025', ln=True, align='C')
    pdf.cell(0, 6, 'Effective January 1, 2024', ln=True, align='C')

    pdf.ln(4)

    # Split text into lines and add to PDF
    pdf.set_font('Helvetica', '', 8)

    for line in CONTRACT_TEXT.split('\n'):
        # Handle different formatting
        if line.startswith('═'):
            pdf.ln(2)
        elif line.startswith('#'):
            pdf.set_font('Helvetica', 'B', 10)
            pdf.multi_cell(0, 4, line.lstrip('#').strip())
            pdf.set_font('Helvetica', '', 8)
        elif line.startswith('##'):
            pdf.set_font('Helvetica', 'B', 9)
            pdf.multi_cell(0, 4, line.lstrip('#').strip())
            pdf.set_font('Helvetica', '', 8)
        elif line.startswith('**') and line.endswith('**'):
            pdf.set_font('Helvetica', 'B', 8)
            pdf.multi_cell(0, 3, line.strip('*'))
            pdf.set_font('Helvetica', '', 8)
        else:
            if line.strip():
                pdf.multi_cell(0, 3, line, max_line_height=pdf.font_size_pt/pdf.k)
            else:
                pdf.ln(1)

    pdf.output(output_path)

    return output_path, CONTRACT_TEXT


def run(db_path: str = './opa.db') -> str:
    """Generate HMO contract PDF and return path."""
    import os

    contract_dir = os.path.join(os.path.dirname(db_path), 'contracts')
    os.makedirs(contract_dir, exist_ok=True)

    output_path = os.path.join(contract_dir, 'hmo_contract_2024.pdf')

    pdf_path, contract_text = generate_hmo_contract_pdf(output_path)

    print(f"  Generated HMO contract PDF: {pdf_path}")
    print(f"  Pages (estimated): ~{len(contract_text) // 2500}")  # Rough estimate

    return pdf_path


if __name__ == '__main__':
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else './opa.db'
    run(db_path)
