"""
Claims Reconciliation Engine.
Matches Claims against ExplanationOfBenefit (EOB) records and identifies discrepancies.
Supports both direct data passing and MongoDB-backed data retrieval.
"""

import logging
from typing import Optional
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DiscrepancyType(str, Enum):
    DENIED = "denied"
    PARTIAL_PAYMENT = "partial_payment"
    OVERPAYMENT = "overpayment"
    UNDERPAYMENT = "underpayment"
    NO_EOB = "no_eob_found"
    NO_CLAIM = "no_claim_found"
    AMOUNT_MISMATCH = "amount_mismatch"


class MatchedPair(BaseModel):
    claim_id: str
    eob_id: str
    claim_amount: float
    paid_amount: float
    patient_responsibility: float = 0.0
    status: str = "matched"
    discrepancy_type: Optional[DiscrepancyType] = None
    discrepancy_amount: float = 0.0
    claim_date: Optional[str] = None
    eob_date: Optional[str] = None
    claim_type: Optional[str] = None
    provider: Optional[str] = None


class UnmatchedItem(BaseModel):
    resource_type: str  # "Claim" or "ExplanationOfBenefit"
    resource_id: str
    amount: float
    date: Optional[str] = None
    status: Optional[str] = None
    reason: str = ""


class ReconciliationResult(BaseModel):
    patient_id: str
    date_range: Optional[str] = None
    total_claims: int = 0
    total_eobs: int = 0
    matched: list[MatchedPair] = Field(default_factory=list)
    unmatched: list[UnmatchedItem] = Field(default_factory=list)
    discrepancies: list[MatchedPair] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)


def _extract_claim_total(claim: dict) -> float:
    total = claim.get("total", {})
    if isinstance(total, dict):
        return float(total.get("value", 0))
    return 0.0


def _extract_claim_date(claim: dict) -> Optional[str]:
    return claim.get("created") or claim.get("billablePeriod", {}).get("start")


def _extract_eob_claim_ref(eob: dict) -> Optional[str]:
    claim_ref = eob.get("claim", {}).get("reference", "")
    if claim_ref.startswith("Claim/"):
        return claim_ref.split("/")[-1]
    if claim_ref.startswith("urn:uuid:"):
        return claim_ref.replace("urn:uuid:", "")
    return claim_ref or None


def _extract_eob_payment(eob: dict) -> float:
    payment = eob.get("payment", {})
    amount = payment.get("amount", {})
    if isinstance(amount, dict):
        return float(amount.get("value", 0))
    return 0.0


def _extract_eob_total_by_category(eob: dict, category: str) -> float:
    for total in eob.get("total", []):
        cat = total.get("category", {})
        for coding in cat.get("coding", []):
            if coding.get("code") == category:
                return float(total.get("amount", {}).get("value", 0))
    return 0.0


def _extract_eob_date(eob: dict) -> Optional[str]:
    return eob.get("created") or eob.get("billablePeriod", {}).get("start")


def _extract_eob_status(eob: dict) -> str:
    return eob.get("outcome", eob.get("status", "unknown"))


def _extract_claim_type(resource: dict) -> Optional[str]:
    type_obj = resource.get("type", {})
    for coding in type_obj.get("coding", []):
        code = coding.get("code", "")
        if code:
            return code
    return None


def _extract_provider(claim: dict) -> Optional[str]:
    provider = claim.get("provider", {})
    return provider.get("display") or provider.get("reference")


def _is_denied(eob: dict) -> bool:
    outcome = eob.get("outcome", "").lower()
    if outcome in ("error", "partial"):
        return True
    payment = _extract_eob_payment(eob)
    submitted = _extract_eob_total_by_category(eob, "submitted")
    if submitted > 10 and payment == 0:
        return True
    return False


def _classify_discrepancy(claim_amount: float, paid_amount: float, is_denied: bool) -> DiscrepancyType:
    if is_denied and paid_amount == 0:
        return DiscrepancyType.DENIED
    if paid_amount > claim_amount:
        return DiscrepancyType.OVERPAYMENT
    if paid_amount < claim_amount * 0.95:
        return DiscrepancyType.UNDERPAYMENT
    return DiscrepancyType.AMOUNT_MISMATCH


def reconcile_claims(
    patient_id: str,
    claims: list[dict],
    eobs: list[dict],
) -> ReconciliationResult:
    """
    Reconcile claims against EOBs.

    Args:
        patient_id: Patient identifier.
        claims: List of FHIR Claim documents (from MongoDB or FHIR API).
        eobs: List of FHIR ExplanationOfBenefit documents.

    Returns:
        ReconciliationResult with matched pairs, discrepancies, and summary.
    """
    result = ReconciliationResult(patient_id=patient_id)
    result.total_claims = len(claims)
    result.total_eobs = len(eobs)

    # Index EOBs by their claim reference
    eob_by_claim_id: dict[str, dict] = {}
    for eob in eobs:
        ref = _extract_eob_claim_ref(eob)
        if ref:
            eob_by_claim_id[ref] = eob

    matched_eob_ids: set[str] = set()

    for claim in claims:
        claim_id = claim.get("id", "unknown")
        claim_amount = _extract_claim_total(claim)
        claim_date = _extract_claim_date(claim)
        claim_type = _extract_claim_type(claim)
        provider = _extract_provider(claim)

        eob = eob_by_claim_id.get(claim_id)

        if eob is None:
            result.unmatched.append(UnmatchedItem(
                resource_type="Claim",
                resource_id=claim_id,
                amount=claim_amount,
                date=claim_date,
                status="no_eob",
                reason="No matching EOB found",
            ))
            continue

        eob_id = eob.get("id", "unknown")
        matched_eob_ids.add(eob_id)
        paid_amount = _extract_eob_payment(eob)
        eob_date = _extract_eob_date(eob)
        denied = _is_denied(eob)

        # Patient responsibility
        patient_resp = _extract_eob_total_by_category(eob, "patientpay")

        # Check for discrepancy
        has_discrepancy = denied or abs(claim_amount - paid_amount) > 0.01

        if has_discrepancy:
            disc_type = _classify_discrepancy(claim_amount, paid_amount, denied)
            disc_amount = paid_amount - claim_amount
            pair = MatchedPair(
                claim_id=claim_id,
                eob_id=eob_id,
                claim_amount=round(claim_amount, 2),
                paid_amount=round(paid_amount, 2),
                patient_responsibility=round(patient_resp, 2),
                status="discrepancy",
                discrepancy_type=disc_type,
                discrepancy_amount=round(disc_amount, 2),
                claim_date=claim_date,
                eob_date=eob_date,
                claim_type=claim_type,
                provider=provider,
            )
            result.discrepancies.append(pair)
        else:
            pair = MatchedPair(
                claim_id=claim_id,
                eob_id=eob_id,
                claim_amount=round(claim_amount, 2),
                paid_amount=round(paid_amount, 2),
                patient_responsibility=round(patient_resp, 2),
                status="matched",
                claim_date=claim_date,
                eob_date=eob_date,
                claim_type=claim_type,
                provider=provider,
            )
            result.matched.append(pair)

    # Unmatched EOBs
    for eob in eobs:
        if eob.get("id") not in matched_eob_ids:
            result.unmatched.append(UnmatchedItem(
                resource_type="ExplanationOfBenefit",
                resource_id=eob.get("id", "unknown"),
                amount=_extract_eob_payment(eob),
                date=_extract_eob_date(eob),
                status=_extract_eob_status(eob),
                reason="No matching Claim found",
            ))

    # Build summary
    total_claimed = sum(m.claim_amount for m in result.matched) + \
                    sum(d.claim_amount for d in result.discrepancies)
    total_paid = sum(m.paid_amount for m in result.matched) + \
                 sum(d.paid_amount for d in result.discrepancies)
    total_discrepancy = sum(abs(d.discrepancy_amount) for d in result.discrepancies)

    result.summary = {
        "total_claims": result.total_claims,
        "total_eobs": result.total_eobs,
        "matched_count": len(result.matched),
        "discrepancy_count": len(result.discrepancies),
        "unmatched_count": len(result.unmatched),
        "total_claimed_amount": round(total_claimed, 2),
        "total_paid_amount": round(total_paid, 2),
        "total_discrepancy_amount": round(total_discrepancy, 2),
        "match_rate": round(len(result.matched) / max(result.total_claims, 1) * 100, 1),
        "discrepancy_breakdown": {},
    }

    for d in result.discrepancies:
        dt = d.discrepancy_type.value if d.discrepancy_type else "unknown"
        if dt not in result.summary["discrepancy_breakdown"]:
            result.summary["discrepancy_breakdown"][dt] = {"count": 0, "total_amount": 0.0}
        result.summary["discrepancy_breakdown"][dt]["count"] += 1
        result.summary["discrepancy_breakdown"][dt]["total_amount"] += abs(d.discrepancy_amount)

    return result


def reconcile_from_mongodb(
    patient_id: str,
    mongodb_client,
    limit: int = 100,
) -> ReconciliationResult:
    """
    Reconcile claims using MongoDB as the data source.

    Args:
        patient_id: Patient identifier (None = all patients).
        mongodb_client: MongoDBClient instance.
        limit: Max records to fetch per collection.

    Returns:
        ReconciliationResult.
    """
    pid = patient_id if patient_id != "all" else None
    claims = mongodb_client.get_claims(patient_id=pid, limit=limit)
    eobs = mongodb_client.get_eobs(limit=limit)
    return reconcile_claims(patient_id or "all", claims, eobs)
