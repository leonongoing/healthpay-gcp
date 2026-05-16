"""
AI-Powered Denial Analysis Engine.
Analyzes claim denials, identifies patterns, and generates appeal recommendations.
Queries MongoDB eobs collection directly.
"""

import logging
from typing import Optional
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DenialCategory(str, Enum):
    CODING_ERROR = "coding_error"
    MISSING_AUTH = "missing_prior_authorization"
    ELIGIBILITY = "eligibility_issue"
    DUPLICATE = "duplicate_claim"
    TIMELY_FILING = "timely_filing"
    MEDICAL_NECESSITY = "medical_necessity"
    BUNDLING = "bundling_issue"
    COORDINATION = "coordination_of_benefits"
    INCOMPLETE_INFO = "incomplete_information"
    OTHER = "other"


class AppealRecommendation(BaseModel):
    priority: str  # "high", "medium", "low"
    estimated_recovery: float = 0.0
    strategy: str = ""
    key_points: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    deadline_note: str = ""


class DenialAnalysis(BaseModel):
    claim_id: str
    eob_id: str
    denied_amount: float
    denial_category: DenialCategory
    denial_reason: str
    root_cause: str
    appeal_recommendation: AppealRecommendation
    similar_denials_count: int = 0
    payer_denial_rate: Optional[float] = None


class PayerProfile(BaseModel):
    payer_name: str
    payer_id: str
    total_claims: int = 0
    denied_claims: int = 0
    denial_rate: float = 0.0
    avg_payment_days: float = 0.0
    top_denial_reasons: list[dict] = Field(default_factory=list)
    total_denied_amount: float = 0.0
    recovery_potential: float = 0.0


class DenialReport(BaseModel):
    patient_id: str
    total_denials: int = 0
    total_denied_amount: float = 0.0
    total_recovery_potential: float = 0.0
    analyses: list[DenialAnalysis] = Field(default_factory=list)
    payer_profiles: list[PayerProfile] = Field(default_factory=list)
    pattern_insights: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)


# Common denial reason codes (CARC - Claim Adjustment Reason Codes)
CARC_MAPPING = {
    "1": ("DEDUCTIBLE", DenialCategory.ELIGIBILITY, "Deductible amount"),
    "2": ("COINSURANCE", DenialCategory.ELIGIBILITY, "Coinsurance amount"),
    "3": ("COPAY", DenialCategory.ELIGIBILITY, "Co-payment amount"),
    "4": ("BUNDLING", DenialCategory.BUNDLING, "Procedure code inconsistent with modifier"),
    "5": ("BUNDLING", DenialCategory.BUNDLING, "Procedure code inconsistent with place of service"),
    "16": ("MISSING_INFO", DenialCategory.INCOMPLETE_INFO, "Claim lacks information for adjudication"),
    "18": ("DUPLICATE", DenialCategory.DUPLICATE, "Exact duplicate claim"),
    "22": ("COORDINATION", DenialCategory.COORDINATION, "Coordination of benefits"),
    "29": ("TIMELY_FILING", DenialCategory.TIMELY_FILING, "Timely filing limit exceeded"),
    "50": ("MEDICAL_NECESSITY", DenialCategory.MEDICAL_NECESSITY, "Not medically necessary"),
    "96": ("MISSING_AUTH", DenialCategory.MISSING_AUTH, "Non-covered charge; prior authorization required"),
    "97": ("BUNDLING", DenialCategory.BUNDLING, "Payment included in allowance for another service"),
    "109": ("MISSING_AUTH", DenialCategory.MISSING_AUTH, "Claim not covered by this payer"),
    "119": ("ELIGIBILITY", DenialCategory.ELIGIBILITY, "Benefit maximum has been reached"),
    "167": ("CODING_ERROR", DenialCategory.CODING_ERROR, "Diagnosis is not covered"),
    "181": ("CODING_ERROR", DenialCategory.CODING_ERROR, "Procedure code was invalid on date of service"),
    "197": ("MISSING_AUTH", DenialCategory.MISSING_AUTH, "Precertification/authorization absent"),
    "236": ("BUNDLING", DenialCategory.BUNDLING, "This procedure or procedure/modifier combination is not compatible"),
    "252": ("MISSING_AUTH", DenialCategory.MISSING_AUTH, "An attachment/other documentation is required"),
}


def _extract_denial_codes(eob: dict) -> list[str]:
    """Extract CARC denial codes from an EOB."""
    codes = []
    for item in eob.get("item", []):
        for adj in item.get("adjudication", []):
            reason = adj.get("reason", {})
            for coding in reason.get("coding", []):
                code = coding.get("code", "")
                if code:
                    codes.append(code)
    # Also check top-level adjudication
    for adj in eob.get("adjudication", []):
        reason = adj.get("reason", {})
        for coding in reason.get("coding", []):
            code = coding.get("code", "")
            if code:
                codes.append(code)
    return list(set(codes))


def _extract_eob_payment(eob: dict) -> float:
    payment = eob.get("payment", {})
    amount = payment.get("amount", {})
    if isinstance(amount, dict):
        return float(amount.get("value", 0))
    return 0.0


def _extract_submitted_amount(eob: dict) -> float:
    for total in eob.get("total", []):
        for coding in total.get("category", {}).get("coding", []):
            if coding.get("code") == "submitted":
                return float(total.get("amount", {}).get("value", 0))
    return 0.0


def _is_denied_eob(eob: dict) -> bool:
    outcome = eob.get("outcome", "").lower()
    if outcome in ("error", "partial"):
        return True
    payment = _extract_eob_payment(eob)
    submitted = _extract_submitted_amount(eob)
    if submitted > 10 and payment == 0:
        return True
    return False


def _get_payer_id(eob: dict) -> str:
    for ins in eob.get("insurance", []):
        ref = ins.get("coverage", {}).get("reference", "")
        display = ins.get("coverage", {}).get("display", "")
        return display or ref or "unknown"
    return "unknown"


def _categorize_denial(codes: list[str]) -> tuple[DenialCategory, str, str]:
    """Return (category, reason, root_cause) from CARC codes."""
    for code in codes:
        if code in CARC_MAPPING:
            _, category, reason = CARC_MAPPING[code]
            root_cause = f"CARC {code}: {reason}"
            return category, reason, root_cause
    return DenialCategory.OTHER, "Unspecified denial", "Denial reason not mapped to CARC"


def _build_appeal_recommendation(
    category: DenialCategory,
    denied_amount: float,
    codes: list[str],
) -> AppealRecommendation:
    """Generate appeal recommendation based on denial category."""
    priority = "high" if denied_amount > 1000 else "medium" if denied_amount > 200 else "low"
    estimated_recovery = denied_amount * 0.65  # industry average ~65% appeal success

    strategies = {
        DenialCategory.CODING_ERROR: (
            "Correct and resubmit with accurate codes",
            ["Review ICD-10/CPT codes for accuracy", "Verify modifier usage", "Check code effective dates"],
        ),
        DenialCategory.MISSING_AUTH: (
            "Submit retroactive authorization or appeal with clinical documentation",
            ["Obtain retroactive authorization if available", "Submit clinical necessity documentation", "Reference payer policy for emergency exceptions"],
        ),
        DenialCategory.ELIGIBILITY: (
            "Verify patient eligibility and resubmit or bill patient",
            ["Confirm coverage dates", "Check coordination of benefits order", "Verify deductible/OOP status"],
        ),
        DenialCategory.DUPLICATE: (
            "Verify original claim status before resubmitting",
            ["Check original claim payment status", "If original unpaid, escalate to payer", "Document submission history"],
        ),
        DenialCategory.TIMELY_FILING: (
            "Submit proof of timely filing with appeal",
            ["Gather original submission confirmation", "Document any payer delays", "Check state prompt pay laws"],
        ),
        DenialCategory.MEDICAL_NECESSITY: (
            "Submit clinical documentation supporting medical necessity",
            ["Attach physician notes and clinical rationale", "Reference clinical guidelines (MCG/InterQual)", "Request peer-to-peer review"],
        ),
        DenialCategory.BUNDLING: (
            "Review bundling rules and resubmit with correct modifiers",
            ["Check NCCI edits", "Add appropriate unbundling modifiers (-59, -XU, -XS)", "Verify separate service documentation"],
        ),
    }

    strategy, key_points = strategies.get(
        category,
        ("Review denial and submit appeal with supporting documentation", ["Gather all relevant documentation", "Contact payer for clarification"]),
    )

    return AppealRecommendation(
        priority=priority,
        estimated_recovery=round(estimated_recovery, 2),
        strategy=strategy,
        key_points=key_points,
        supporting_evidence=[f"CARC code(s): {', '.join(codes)}" if codes else "No specific codes found"],
        deadline_note="Most payers require appeals within 60-180 days of denial date",
    )


def analyze_denials(
    patient_id: str,
    claims: list[dict],
    eobs: list[dict],
) -> DenialReport:
    """
    Analyze denied EOBs and generate appeal recommendations.

    Args:
        patient_id: Patient identifier.
        claims: List of FHIR Claim documents.
        eobs: List of FHIR ExplanationOfBenefit documents.

    Returns:
        DenialReport with analyses, payer profiles, and action items.
    """
    report = DenialReport(patient_id=patient_id)

    claims_by_id = {c.get("id", ""): c for c in claims}
    payer_stats: dict[str, dict] = {}

    for eob in eobs:
        if not _is_denied_eob(eob):
            continue

        eob_id = eob.get("id", "unknown")
        claim_ref = eob.get("claim", {}).get("reference", "")
        claim_id = claim_ref.split("/")[-1] if "/" in claim_ref else claim_ref or "unknown"

        denied_amount = _extract_submitted_amount(eob) or _extract_eob_payment(eob)
        if denied_amount == 0:
            denied_amount = 500.0  # fallback estimate

        codes = _extract_denial_codes(eob)
        category, reason, root_cause = _categorize_denial(codes)
        appeal_rec = _build_appeal_recommendation(category, denied_amount, codes)

        analysis = DenialAnalysis(
            claim_id=claim_id,
            eob_id=eob_id,
            denied_amount=denied_amount,
            denial_category=category,
            denial_reason=reason,
            root_cause=root_cause,
            appeal_recommendation=appeal_rec,
        )
        report.analyses.append(analysis)
        report.total_denied_amount += denied_amount
        report.total_recovery_potential += appeal_rec.estimated_recovery

        # Track payer stats
        payer_id = _get_payer_id(eob)
        if payer_id not in payer_stats:
            payer_stats[payer_id] = {"total": 0, "denied": 0, "denied_amount": 0.0, "reasons": {}}
        payer_stats[payer_id]["total"] += 1
        payer_stats[payer_id]["denied"] += 1
        payer_stats[payer_id]["denied_amount"] += denied_amount
        payer_stats[payer_id]["reasons"][reason] = payer_stats[payer_id]["reasons"].get(reason, 0) + 1

    # Count non-denied EOBs for payer totals
    for eob in eobs:
        if not _is_denied_eob(eob):
            payer_id = _get_payer_id(eob)
            if payer_id not in payer_stats:
                payer_stats[payer_id] = {"total": 0, "denied": 0, "denied_amount": 0.0, "reasons": {}}
            payer_stats[payer_id]["total"] += 1

    # Build payer profiles
    for payer_id, stats in payer_stats.items():
        total = stats["total"]
        denied = stats["denied"]
        profile = PayerProfile(
            payer_name=payer_id,
            payer_id=payer_id,
            total_claims=total,
            denied_claims=denied,
            denial_rate=round(denied / max(total, 1) * 100, 1),
            total_denied_amount=round(stats["denied_amount"], 2),
            recovery_potential=round(stats["denied_amount"] * 0.65, 2),
            top_denial_reasons=[
                {"reason": r, "count": c}
                for r, c in sorted(stats["reasons"].items(), key=lambda x: -x[1])[:5]
            ],
        )
        report.payer_profiles.append(profile)

    report.total_denials = len(report.analyses)
    report.total_denied_amount = round(report.total_denied_amount, 2)
    report.total_recovery_potential = round(report.total_recovery_potential, 2)

    # Pattern insights
    if report.total_denials > 0:
        category_counts: dict[str, int] = {}
        for a in report.analyses:
            cat = a.denial_category.value
            category_counts[cat] = category_counts.get(cat, 0) + 1

        top_cat = max(category_counts, key=lambda k: category_counts[k])
        report.pattern_insights.append(
            f"Most common denial category: {top_cat} ({category_counts[top_cat]} denials)"
        )
        if report.total_recovery_potential > 0:
            report.pattern_insights.append(
                f"Estimated recovery potential: ${report.total_recovery_potential:,.2f}"
            )

    # Action items
    high_priority = [a for a in report.analyses if a.appeal_recommendation.priority == "high"]
    if high_priority:
        report.action_items.append(
            f"Immediately appeal {len(high_priority)} high-priority denial(s) totaling "
            f"${sum(a.denied_amount for a in high_priority):,.2f}"
        )
    report.action_items.append("Review payer contracts for denial pattern trends")
    report.action_items.append("Implement pre-submission claim scrubbing to reduce coding errors")

    return report


def find_similar_denials(
    denial_code: str,
    eobs: list[dict],
    limit: int = 5,
) -> list[dict]:
    """
    Find EOBs with similar denial codes using simple text matching.
    (Vector Search will be added in Phase 3.)

    Args:
        denial_code: CARC code or denial reason text to match.
        eobs: List of EOB documents to search.
        limit: Maximum results to return.

    Returns:
        List of matching EOB summaries.
    """
    results = []
    denial_code_lower = denial_code.lower()

    for eob in eobs:
        if not _is_denied_eob(eob):
            continue

        codes = _extract_denial_codes(eob)
        # Direct code match
        if denial_code in codes:
            results.append({
                "eob_id": eob.get("id", "unknown"),
                "match_type": "exact_code",
                "codes": codes,
                "denied_amount": _extract_submitted_amount(eob),
                "payer": _get_payer_id(eob),
            })
            continue

        # Text match against CARC descriptions
        for code in codes:
            if code in CARC_MAPPING:
                _, _, description = CARC_MAPPING[code]
                if denial_code_lower in description.lower():
                    results.append({
                        "eob_id": eob.get("id", "unknown"),
                        "match_type": "text_match",
                        "codes": codes,
                        "denied_amount": _extract_submitted_amount(eob),
                        "payer": _get_payer_id(eob),
                    })
                    break

        if len(results) >= limit:
            break

    return results[:limit]


def run_denial_analysis(
    patient_id: Optional[str],
    mongodb_client,
    limit: int = 50,
) -> DenialReport:
    """
    Convenience wrapper: fetch data from MongoDB and run denial analysis.

    Args:
        patient_id: Filter by patient (None = all patients).
        mongodb_client: MongoDBClient instance.
        limit: Max records to fetch.

    Returns:
        DenialReport.
    """
    pid = patient_id if patient_id and patient_id != "all" else None
    claims = mongodb_client.get_claims(patient_id=pid, limit=limit)
    eobs = mongodb_client.get_eobs(limit=limit)
    return analyze_denials(patient_id or "all", claims, eobs)
