"""
Financial Vitals — A/R Aging Dashboard.
Aggregates claims data from MongoDB to provide financial health metrics.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ARAgingBucket(BaseModel):
    bucket: str          # e.g. "0-30", "31-60", "61-90", "91-120", "120+"
    claim_count: int = 0
    total_amount: float = 0.0
    percentage: float = 0.0


class ARAgingReport(BaseModel):
    as_of_date: str
    total_ar: float = 0.0
    buckets: list[ARAgingBucket] = Field(default_factory=list)
    avg_days_outstanding: float = 0.0


class CollectionRateReport(BaseModel):
    period_label: str
    total_billed: float = 0.0
    total_collected: float = 0.0
    collection_rate: float = 0.0   # 0-100 %
    adjustment_rate: float = 0.0
    write_off_rate: float = 0.0


class PayerPerformance(BaseModel):
    payer_id: str
    payer_name: str
    total_claims: int = 0
    total_billed: float = 0.0
    total_paid: float = 0.0
    payment_rate: float = 0.0
    avg_days_to_pay: float = 0.0
    denial_rate: float = 0.0


class FinancialVitalsReport(BaseModel):
    generated_at: str
    ar_aging: Optional[ARAgingReport] = None
    collection_rate: Optional[CollectionRateReport] = None
    payer_performance: list[PayerPerformance] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers for computing from in-memory claim/eob lists
# ---------------------------------------------------------------------------

def _days_outstanding(claim: dict) -> int:
    """Days since claim was created."""
    created = claim.get("created") or claim.get("billablePeriod", {}).get("start")
    if not created:
        return 0
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return max(0, (now - dt).days)
    except Exception:
        return 0


def _claim_total(claim: dict) -> float:
    total = claim.get("total", {})
    if isinstance(total, dict):
        return float(total.get("value", 0))
    return 0.0


def _eob_payment(eob: dict) -> float:
    payment = eob.get("payment", {})
    amount = payment.get("amount", {})
    if isinstance(amount, dict):
        return float(amount.get("value", 0))
    return 0.0


def _eob_submitted(eob: dict) -> float:
    for total in eob.get("total", []):
        for coding in total.get("category", {}).get("coding", []):
            if coding.get("code") == "submitted":
                return float(total.get("amount", {}).get("value", 0))
    return 0.0


def _payer_id(eob: dict) -> str:
    for ins in eob.get("insurance", []):
        display = ins.get("coverage", {}).get("display", "")
        ref = ins.get("coverage", {}).get("reference", "")
        return display or ref or "unknown"
    return "unknown"


# ---------------------------------------------------------------------------
# Core computation functions (work on in-memory lists)
# ---------------------------------------------------------------------------

def compute_ar_aging(claims: list[dict], eobs: list[dict]) -> ARAgingReport:
    """
    Compute A/R aging from claims and EOBs.
    Unpaid claims (no matching EOB payment) are bucketed by days outstanding.
    """
    # Build set of paid claim IDs
    paid_claim_ids: set[str] = set()
    for eob in eobs:
        ref = eob.get("claim", {}).get("reference", "")
        cid = ref.split("/")[-1] if "/" in ref else ref
        if _eob_payment(eob) > 0:
            paid_claim_ids.add(cid)

    buckets = {
        "0-30": ARAgingBucket(bucket="0-30"),
        "31-60": ARAgingBucket(bucket="31-60"),
        "61-90": ARAgingBucket(bucket="61-90"),
        "91-120": ARAgingBucket(bucket="91-120"),
        "120+": ARAgingBucket(bucket="120+"),
    }

    total_ar = 0.0
    total_days = 0
    unpaid_count = 0

    for claim in claims:
        cid = claim.get("id", "")
        if cid in paid_claim_ids:
            continue
        amount = _claim_total(claim)
        days = _days_outstanding(claim)
        total_ar += amount
        total_days += days
        unpaid_count += 1

        if days <= 30:
            key = "0-30"
        elif days <= 60:
            key = "31-60"
        elif days <= 90:
            key = "61-90"
        elif days <= 120:
            key = "91-120"
        else:
            key = "120+"

        buckets[key].claim_count += 1
        buckets[key].total_amount += amount

    # Compute percentages
    for b in buckets.values():
        b.total_amount = round(b.total_amount, 2)
        b.percentage = round(b.total_amount / total_ar * 100, 1) if total_ar > 0 else 0.0

    return ARAgingReport(
        as_of_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        total_ar=round(total_ar, 2),
        buckets=list(buckets.values()),
        avg_days_outstanding=round(total_days / unpaid_count, 1) if unpaid_count > 0 else 0.0,
    )


def compute_collection_rate(claims: list[dict], eobs: list[dict]) -> CollectionRateReport:
    """Compute collection rate from claims and EOBs."""
    eob_by_claim: dict[str, dict] = {}
    for eob in eobs:
        ref = eob.get("claim", {}).get("reference", "")
        cid = ref.split("/")[-1] if "/" in ref else ref
        eob_by_claim[cid] = eob

    total_billed = 0.0
    total_collected = 0.0

    for claim in claims:
        cid = claim.get("id", "")
        billed = _claim_total(claim)
        total_billed += billed
        eob = eob_by_claim.get(cid)
        if eob:
            total_collected += _eob_payment(eob)

    collection_rate = round(total_collected / total_billed * 100, 1) if total_billed > 0 else 0.0

    return CollectionRateReport(
        period_label="all_time",
        total_billed=round(total_billed, 2),
        total_collected=round(total_collected, 2),
        collection_rate=collection_rate,
        adjustment_rate=round((total_billed - total_collected) / total_billed * 100, 1) if total_billed > 0 else 0.0,
        write_off_rate=0.0,  # Requires write-off data
    )


def compute_payer_performance(eobs: list[dict]) -> list[PayerPerformance]:
    """Compute per-payer performance metrics from EOBs."""
    from collections import defaultdict
    stats: dict[str, dict] = defaultdict(lambda: {
        "total_claims": 0,
        "total_billed": 0.0,
        "total_paid": 0.0,
        "denied": 0,
    })

    for eob in eobs:
        pid = _payer_id(eob)
        submitted = _eob_submitted(eob)
        paid = _eob_payment(eob)
        stats[pid]["total_claims"] += 1
        stats[pid]["total_billed"] += submitted
        stats[pid]["total_paid"] += paid
        if submitted > 10 and paid == 0:
            stats[pid]["denied"] += 1

    result = []
    for payer_id, s in stats.items():
        total_claims = s["total_claims"]
        total_billed = s["total_billed"]
        total_paid = s["total_paid"]
        denied = s["denied"]
        result.append(PayerPerformance(
            payer_id=payer_id,
            payer_name=payer_id,
            total_claims=total_claims,
            total_billed=round(total_billed, 2),
            total_paid=round(total_paid, 2),
            payment_rate=round(total_paid / total_billed * 100, 1) if total_billed > 0 else 0.0,
            avg_days_to_pay=0.0,  # Requires payment date data
            denial_rate=round(denied / total_claims * 100, 1) if total_claims > 0 else 0.0,
        ))
    return result


# ---------------------------------------------------------------------------
# High-level API — uses MongoDBClient
# ---------------------------------------------------------------------------

class FinancialVitals:
    """
    A/R aging dashboard backed by MongoDB.
    Falls back gracefully when MongoDB is in mock mode (returns empty/zero metrics).
    """

    def __init__(self, mongodb_client=None):
        if mongodb_client is None:
            from src.mongodb_client import MongoDBClient
            mongodb_client = MongoDBClient()
        self.db = mongodb_client

    def get_ar_aging(self, patient_id: Optional[str] = None, limit: int = 500) -> ARAgingReport:
        """Return A/R aging report."""
        claims = self.db.get_claims(patient_id=patient_id, limit=limit)
        eobs = self.db.get_eobs(limit=limit)
        return compute_ar_aging(claims, eobs)

    def get_collection_rate(self, patient_id: Optional[str] = None, limit: int = 500) -> CollectionRateReport:
        """Return collection rate report."""
        claims = self.db.get_claims(patient_id=patient_id, limit=limit)
        eobs = self.db.get_eobs(limit=limit)
        return compute_collection_rate(claims, eobs)

    def get_payer_performance(self, limit: int = 500) -> list[PayerPerformance]:
        """Return per-payer performance metrics."""
        eobs = self.db.get_eobs(limit=limit)
        return compute_payer_performance(eobs)

    def get_full_report(self, patient_id: Optional[str] = None, limit: int = 500) -> FinancialVitalsReport:
        """Return a combined financial vitals report."""
        from datetime import datetime, timezone
        claims = self.db.get_claims(patient_id=patient_id, limit=limit)
        eobs = self.db.get_eobs(limit=limit)
        return FinancialVitalsReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            ar_aging=compute_ar_aging(claims, eobs),
            collection_rate=compute_collection_rate(claims, eobs),
            payer_performance=compute_payer_performance(eobs),
        )
