"""
Coding Optimization Advisor.
Analyzes historical denial patterns to suggest ICD-10/CPT coding improvements.
"""

import logging
from typing import Optional
from collections import defaultdict

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CodingSuggestion(BaseModel):
    claim_id: str
    current_codes: list[str] = Field(default_factory=list)
    issue_type: str  # "specificity", "modifier", "bundling", "sequencing", "documentation"
    severity: str  # "high", "medium", "low"
    suggestion: str
    rationale: str
    estimated_impact: str = ""


class CodingPattern(BaseModel):
    pattern_name: str
    occurrence_count: int = 0
    affected_amount: float = 0.0
    description: str = ""
    fix_recommendation: str = ""


class CodingReport(BaseModel):
    patient_id: str
    total_claims_reviewed: int = 0
    claims_with_issues: int = 0
    suggestions: list[CodingSuggestion] = Field(default_factory=list)
    patterns: list[CodingPattern] = Field(default_factory=list)
    overall_coding_score: float = 0.0  # 0-100
    estimated_revenue_recovery: float = 0.0
    top_recommendations: list[str] = Field(default_factory=list)


# Common coding issues by claim type
CODING_RULES = {
    "professional": {
        "high_value_threshold": 5000,
        "common_issues": [
            "Verify E/M level matches documentation complexity",
            "Check modifier usage (-25, -59, -76, -77)",
            "Ensure diagnosis specificity (ICD-10 to highest level)",
        ],
    },
    "institutional": {
        "high_value_threshold": 10000,
        "common_issues": [
            "Verify DRG assignment accuracy",
            "Check for CC/MCC capture opportunities",
            "Review revenue codes match service descriptions",
        ],
    },
    "pharmacy": {
        "high_value_threshold": 2000,
        "common_issues": [
            "Verify NDC codes are current",
            "Check quantity and days supply accuracy",
            "Ensure prior authorization is documented",
        ],
    },
}


def _extract_codes(claim: dict) -> list[str]:
    """Extract procedure/diagnosis codes from a claim."""
    codes = []
    # Diagnosis codes
    for diag in claim.get("diagnosis", []):
        for coding in diag.get("diagnosisCodeableConcept", {}).get("coding", []):
            code = coding.get("code", "")
            if code:
                codes.append(f"ICD:{code}")

    # Procedure codes from items
    for item in claim.get("item", []):
        for coding in item.get("productOrService", {}).get("coding", []):
            code = coding.get("code", "")
            if code:
                codes.append(f"CPT:{code}")
        # Modifiers
        for mod in item.get("modifier", []):
            for coding in mod.get("coding", []):
                codes.append(f"MOD:{coding.get('code', '')}")

    return codes


def _get_claim_type(claim: dict) -> str:
    for coding in claim.get("type", {}).get("coding", []):
        return coding.get("code", "unknown")
    return "unknown"


def _analyze_claim_coding(
    claim: dict,
    eob: Optional[dict],
    denial_history: dict,
) -> list[CodingSuggestion]:
    """Analyze a single claim for coding optimization opportunities."""
    suggestions = []
    claim_id = claim.get("id", "")
    codes = _extract_codes(claim)
    claim_type = _get_claim_type(claim)
    claim_amount = float(claim.get("total", {}).get("value", 0))

    # Check if this claim was denied
    is_denied = False
    payment = 0.0
    if eob:
        payment = float(eob.get("payment", {}).get("amount", {}).get("value", 0))
        is_denied = (payment == 0 and claim_amount > 10)

    # Rule 1: Diagnosis specificity
    icd_codes = [c for c in codes if c.startswith("ICD:")]
    short_codes = [c for c in icd_codes if len(c.split(":")[1]) < 5]
    if short_codes:
        suggestions.append(CodingSuggestion(
            claim_id=claim_id,
            current_codes=short_codes,
            issue_type="specificity",
            severity="high" if is_denied else "medium",
            suggestion="Increase ICD-10 code specificity to highest available level",
            rationale=f"Found {len(short_codes)} codes with fewer than 5 characters. "
                      "Truncated codes are a leading cause of denials.",
            estimated_impact=f"${claim_amount * 0.3:,.2f} potential recovery" if is_denied else "Preventive",
        ))

    # Rule 2: Missing modifiers on high-value claims
    cpt_codes = [c for c in codes if c.startswith("CPT:")]
    mod_codes = [c for c in codes if c.startswith("MOD:")]
    if len(cpt_codes) > 1 and not mod_codes:
        suggestions.append(CodingSuggestion(
            claim_id=claim_id,
            current_codes=cpt_codes,
            issue_type="modifier",
            severity="medium",
            suggestion="Consider adding modifier -59 (Distinct Procedural Service) for multiple procedures",
            rationale=f"Claim has {len(cpt_codes)} procedure codes without modifiers. "
                      "This may trigger bundling edits.",
            estimated_impact="Prevents potential bundling denial",
        ))

    # Rule 3: High-value claim without sufficient documentation codes
    rules = CODING_RULES.get(claim_type, CODING_RULES.get("professional", {}))
    threshold = rules.get("high_value_threshold", 5000)
    if claim_amount > threshold and len(icd_codes) < 2:
        suggestions.append(CodingSuggestion(
            claim_id=claim_id,
            current_codes=codes,
            issue_type="documentation",
            severity="medium",
            suggestion="Add supporting diagnosis codes to justify high-value claim",
            rationale=f"${claim_amount:,.2f} claim with only {len(icd_codes)} diagnosis code(s). "
                      "Additional codes strengthen medical necessity.",
            estimated_impact="Reduces denial risk for high-value claims",
        ))

    # Rule 4: Denied claim — suggest review
    if is_denied and not suggestions:
        suggestions.append(CodingSuggestion(
            claim_id=claim_id,
            current_codes=codes,
            issue_type="sequencing",
            severity="high",
            suggestion="Review primary diagnosis sequencing and code selection for denied claim",
            rationale="Claim was denied. Verify primary diagnosis is the most specific "
                      "code that justifies the service performed.",
            estimated_impact=f"${claim_amount:,.2f} potential recovery on appeal",
        ))

    return suggestions


def suggest_coding_optimization(
    patient_id: str,
    claims: list[dict],
    eobs: list[dict],
) -> CodingReport:
    """
    Analyze claims for coding optimization opportunities.
    """
    report = CodingReport(patient_id=patient_id)
    report.total_claims_reviewed = len(claims)

    # Build EOB lookup
    eob_by_claim = {}
    for eob in eobs:
        ref = eob.get("claim", {}).get("reference", "")
        cid = ref.split("/")[-1] if "/" in ref else ref
        eob_by_claim[cid] = eob

    # Build denial history
    denial_history = defaultdict(int)
    for eob in eobs:
        payment = float(eob.get("payment", {}).get("amount", {}).get("value", 0))
        submitted = 0.0
        for total in eob.get("total", []):
            for coding in total.get("category", {}).get("coding", []):
                if coding.get("code") == "submitted":
                    submitted = float(total.get("amount", {}).get("value", 0))
        if payment == 0 and submitted > 10:
            denial_history["total_denials"] += 1

    # Analyze each claim
    issue_type_counts = defaultdict(int)
    total_recovery = 0.0

    for claim in claims:
        claim_id = claim.get("id", "")
        eob = eob_by_claim.get(claim_id)
        suggestions = _analyze_claim_coding(claim, eob, denial_history)

        if suggestions:
            report.claims_with_issues += 1
            report.suggestions.extend(suggestions)
            for s in suggestions:
                issue_type_counts[s.issue_type] += 1

    # Build patterns
    for issue_type, count in sorted(issue_type_counts.items(), key=lambda x: x[1], reverse=True):
        affected = [s for s in report.suggestions if s.issue_type == issue_type]
        pattern = CodingPattern(
            pattern_name=issue_type.replace("_", " ").title(),
            occurrence_count=count,
            description=f"Found {count} claims with {issue_type.replace('_', ' ')} issues",
        )

        if issue_type == "specificity":
            pattern.fix_recommendation = "Implement ICD-10 specificity validation in claim scrubbing workflow"
        elif issue_type == "modifier":
            pattern.fix_recommendation = "Add modifier review step for multi-procedure claims"
        elif issue_type == "documentation":
            pattern.fix_recommendation = "Require minimum 2 diagnosis codes for claims over threshold"
        elif issue_type == "sequencing":
            pattern.fix_recommendation = "Review denied claims for primary diagnosis accuracy"

        report.patterns.append(pattern)

    # Scoring
    if report.total_claims_reviewed > 0:
        issue_rate = report.claims_with_issues / report.total_claims_reviewed
        report.overall_coding_score = round(max(0, (1 - issue_rate) * 100), 1)
    else:
        report.overall_coding_score = 100.0

    # Top recommendations
    high_sev = [s for s in report.suggestions if s.severity == "high"]
    if high_sev:
        report.top_recommendations.append(
            f"Address {len(high_sev)} high-severity coding issues immediately"
        )
    if issue_type_counts.get("specificity", 0) > 3:
        report.top_recommendations.append(
            "Implement automated ICD-10 specificity checks in billing workflow"
        )
    if issue_type_counts.get("modifier", 0) > 2:
        report.top_recommendations.append(
            "Review modifier usage guidelines with coding team"
        )

    return report
