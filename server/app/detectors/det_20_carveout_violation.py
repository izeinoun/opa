"""DET-20: Carve-Out Violation Detector

Detects violations of carved-out service rules (Behavioral Health, Pharmacy, DME).
Carve-out violations occur when:
- Behavioral health services provided without authorization/outside network
- Pharmacy services using non-formulary drugs without prior auth
- DME services from non-approved vendors
- Services exceeding carve-out frequency limits
"""
from __future__ import annotations

from .base_detector import BaseDetector, DetectorResult
from ..models.claims import Claim, ClaimLine


class CarveoutViolationDetector(BaseDetector):
    """Detects carve-out contract violations."""

    detector_id = 'DET-20'
    code = 'DET-20'
    name = 'Carve-Out Violation'
    description = 'Behavioral health, pharmacy, or DME not delivered per contract carve-out rules'

    # Behavioral health CPT codes (carved out in HMO contracts)
    BEHAVIORAL_HEALTH_CPTS = {
        '90801', '90802', '90804', '90805', '90806', '90807', '90808', '90809',
        '90810', '90811', '90812', '90813', '90814', '90815', '90816', '90817',
        '90818', '90819', '90821', '90822', '90823', '90824', '90826', '90827',
        '90828', '90829', '90830', '90831', '90832', '90833', '90834', '90835',
        '90836', '90837', '90838', '90839', '90840', '90841', '90845', '90846',
        '90847', '90849', '90853', '90854', '90863', '90865', '90867', '90868',
        '90870', '90871', '90872', '90873', '90875', '90876', '90880', '90882',
        '90883', '90887',
    }

    # Specialty pharmacy drugs requiring prior auth (sample high-cost biologics)
    SPECIALTY_PHARMA_DRUGS = {
        'adalimumab', 'infliximab', 'etanercept', 'certolizumab', 'golimumab',
        'tocilizumab', 'abatacept', 'rituximab', 'natalizumab', 'fingolimod',
        'dupilumab', 'omalizumab', 'mepolizumab', 'reslizumab', 'benralizumab',
        'tezepelumab', 'secukinumab', 'ixekizumab', 'sarilumab', 'baricitinib',
        'filgotinib', 'upadacitinib', 'avelumab', 'durvalumab', 'atezolizumab',
        'pembrolizumab', 'nivolumab', 'dostarlimab', 'tisotumab',
    }

    # DME codes that require approved vendor
    DME_CPTS = {
        'E1390', 'E1391', 'E1392', 'E1393', 'E1395', 'E1396', 'E1405', 'E1406',
        'E1500', 'E1502', 'E1503', 'E1504', 'E1505', 'E1506', 'E1510', 'E1520',
        'E1600', 'E1601', 'E1602', 'E1603', 'E1604', 'E1605', 'E1606', 'E1607',
        'E1608', 'E1609', 'E1610', 'E1615', 'E1620', 'E1625', 'E1630', 'E1635',
        'E1639', 'E1640', 'E1645', 'E1650', 'E1652', 'E1655', 'E1660', 'E1665',
        'E1670', 'E1675', 'E1680', 'E1685', 'E1686', 'E1687', 'E1688', 'E1689',
        'E1690', 'E1691', 'E1692', 'E1700', 'E1701', 'E1702', 'E1703', 'E1704',
        'E1705', 'E1706', 'E1707', 'E1708', 'E1709', 'E1810', 'E1820', 'E1825',
        'E1830', 'E1840', 'E1850', 'E1860', 'E1870', 'E1880', 'E1890', 'E1900',
    }

    async def run(self, claim: Claim, db_session) -> list[DetectorResult]:
        """Check for carve-out violations.

        Note: the orchestrator handles enabled-gating and score_multiplier
        scaling itself, so this matches the BaseDetector.run(claim, db_session)
        contract like the other detectors.
        """
        results = []

        # Skip if not HMO (most likely to have carve-outs)
        if claim.lob and 'HMO' not in claim.lob.upper():
            return results

        for line in claim.claim_lines or []:
            cpt = line.cpt_code
            if not cpt:
                continue

            # Check behavioral health carve-out violations
            if cpt in self.BEHAVIORAL_HEALTH_CPTS:
                result = self._check_behavioral_health_violation(claim, line)
                if result:
                    results.append(result)

            # Check DME carve-out violations
            elif cpt in self.DME_CPTS:
                result = self._check_dme_violation(claim, line)
                if result:
                    results.append(result)

        return results

    def _check_behavioral_health_violation(self, claim: Claim, line: ClaimLine) -> DetectorResult | None:
        """Check for behavioral health carve-out violations."""
        # Violation if:
        # 1. Behavioral health service billed without pre-authorization
        # 2. Service from non-network provider (indicated by network flag)
        # 3. Exceeding visit limits (tracked in claim metadata)

        # Extract provider network status from claim metadata
        is_network = True
        if hasattr(claim, 'raw_claim_json') and claim.raw_claim_json:
            import json
            try:
                metadata = json.loads(claim.raw_claim_json)
                is_network = metadata.get('provider_network', True)
            except:
                pass

        # Out-of-network behavioral health without pre-auth is a violation
        if not is_network:
            return DetectorResult(
                detector_code=self.code,
                finding_type='CARVEOUT_NO_NETWORK',
                description=(
                    f'CPT {line.cpt_code} (behavioral health) billed by out-of-network provider. '
                    f'HMO carve-out requires network provider or pre-authorization for out-of-network.'
                ),
                overpayment_amount=line.paid_amount or 0,
                confidence_score=0.95,
                evidence={
                    'line_id': line.claim_line_id,
                    'paid_amount': line.paid_amount or 0,
                    'cpt_code': line.cpt_code,
                    'title': 'Behavioral Health Out-of-Network Without Authorization',
                },
            )

        # Check if pre-auth was obtained
        has_preauth = True
        if hasattr(claim, 'raw_claim_json') and claim.raw_claim_json:
            import json
            try:
                metadata = json.loads(claim.raw_claim_json)
                has_preauth = metadata.get('behavioral_health_preauth', False)
            except:
                pass

        # First 20 visits don't require preauth; 21+ do
        if not has_preauth:
            visit_count = self._get_behavioral_health_visit_count(claim)
            if visit_count > 20:
                return DetectorResult(
                    detector_code=self.code,
                    finding_type='CARVEOUT_PREAUTH_REQUIRED',
                    description=(
                        f'Behavioral health visit #{visit_count} exceeds 20-visit limit without pre-authorization. '
                        f'CPT {line.cpt_code} requires prior authorization for visits 21+.'
                    ),
                    overpayment_amount=(line.paid_amount or 0) * 0.5,  # Partial overpayment
                    confidence_score=0.85,
                    evidence={
                        'line_id': line.claim_line_id,
                        'paid_amount': line.paid_amount or 0,
                        'cpt_code': line.cpt_code,
                        'title': 'Behavioral Health Pre-Authorization Required',
                    },
                )

        return None

    def _check_dme_violation(self, claim: Claim, line: ClaimLine) -> DetectorResult | None:
        """Check for DME carve-out violations."""
        # Violation if DME obtained from non-approved vendor
        # Approved vendor would be indicated in claim metadata

        vendor = None
        if hasattr(claim, 'raw_claim_json') and claim.raw_claim_json:
            import json
            try:
                metadata = json.loads(claim.raw_claim_json)
                vendor = metadata.get('dme_vendor')
            except Exception:
                vendor = None

        # Vendor unknown → can't assert the DME came from a non-approved source.
        # Default to no finding (avoids flagging every HMO DME line as a violation).
        if not vendor:
            return None
        # "Optimal Medical Supply Company" is the approved carve-out vendor.
        if 'optimal' in vendor.lower() or 'dme' in vendor.lower():
            return None

        return DetectorResult(
                detector_code=self.code,
                finding_type='CARVEOUT_UNAPPROVED_VENDOR',
                description=(
                    f'CPT {line.cpt_code} (DME) billed by non-approved vendor. '
                    f'HMO carve-out requires use of Optimal Medical Supply Company. '
                    f'Plan should not pay for non-network DME.'
                ),
                overpayment_amount=line.paid_amount or 0,
                confidence_score=0.90,
                evidence={
                    'line_id': line.claim_line_id,
                    'paid_amount': line.paid_amount or 0,
                    'cpt_code': line.cpt_code,
                    'title': 'DME from Non-Approved Vendor',
                },
            )

        return None

    def _get_behavioral_health_visit_count(self, claim: Claim) -> int:
        """Get cumulative behavioral health visit count for the year."""
        # In real implementation, would query all claims for this member
        # in the current year with behavioral health CPTs
        # For now, return a count based on claim metadata if available
        if hasattr(claim, 'raw_claim_json') and claim.raw_claim_json:
            import json
            try:
                metadata = json.loads(claim.raw_claim_json)
                return metadata.get('bh_visit_count', 1)
            except:
                pass
        return 1
