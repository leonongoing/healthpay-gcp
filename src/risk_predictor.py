"""
Payment Risk Predictor.
Predicts claim payment probability based on historical patterns.
"""

import logging
from typing import Optional
from collections import defaultdict

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RiskFactor(BaseModel):
    factor: str
    impact: str  # "positive", "negative", "neutral"
    detail: str
    weight: float = 0.0


class PaymentPrediction(BaseModel):
    claim_id: str
    patient_id: str
    claim_amount: float
    predicted_payment: float
    payment_probability: float  # 0.0 - 1.0
    risk_level: str  # "low", "medium", "high"
    risk_score: float  # 0-100, higher = riskier
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    recommendation: str = ""


class RiskReport(BaseModel):
    total_claims_analyzed: int = 0
    predictions: list[PaymentPrediction] = Field(default_factory=list)
    portfolio_risk_score: float = 0.0
    total_at_risk_amount: float = 0.0
    risk_distribution: dict = Field(default_factory=dict)


def _build_payer_history(eobs: list[dict]) -> dict:
    """Build payer payment history from EOBs."""
    payer_stats = defaultdict(lambda: {
        "total": 0, "denied": 0, "paid_amounts": [],
        "submitted_amounts": [], "denial_reasons": defaultdict(int)
    })

    for eob in eobs:
        # Get payer
        payer_ref = "unknown"
        for ins in eob.get("insurance", []):
            payer_ref = ins.get("coverage", {}).get("display", 
                       ins.get("coverage", {}).get("reference", "unknown"))
            break

        payment = float(eob.get("payment", {}).get("amount", {}).get("value", 0))
        submitted = 0.0
        for total in eob.get("total", []):
            for coding in total.get("category", {}).get("coding", []):
                if coding.get("code") == "submitted":
                    submitted = float(total.get("amount", {}).get("value", 0))

        payer_stats[payer_ref]["total"] += 1
        payer_stats[payer_ref]["submitted_amounts"].append(submitted)
        payer_stats[payer_ref]["paid_amounts"].append(payment)

        if payment == 0 and submitted > 10:
            payer_stats[payer_ref]["denied"] += 1

    return dict(payer_stats)


def _build_type_history(claims: list[dict], eobs: list[dict]) -> dict:
    """Build claim type payment history."""
    eob_by_claim = {}
    for eob in eobs:
        ref = eob.get("claim", {}).get("reference", "")
        cid = ref.split("/")[-1] if "/" in ref else ref
        eob_by_claim[cid] = eob

    type_stats = defaultdict(lambda: {"total": 0, "denied": 0, "amounts": []})

    for claim in claims:
        cid = claim.get("id", "")
        claim_type = "unknown"
        for coding in claim.get("type", {}).get("coding", []):
            claim_type = coding.get("code", "unknown")
            break

        amount = float(claim.get("total", {}).get("value", 0))
        eob = eob_by_claim.get(cid)
        payment = float(eob.get("payment", {}).get("amount", {}).get("value", 0)) if eob else 0

        type_stats[claim_type]["total"] += 1
        type_stats[claim_type]["amounts"].append(amount)
        if payment == 0 and amount > 10:
            type_stats[claim_type]["denied"] += 1

    return dict(type_stats)


def predict_payment_risk(
    target_claims: list[dict],
    historical_claims: list[dict],
    historical_eobs: list[dict],
    patient_id: str = "",
) -> RiskReport:
    """
    Predict payment risk for target claims based on historical patterns.
    """
    report = RiskReport()
    payer_history = _build_payer_history(historical_eobs)
    type_history = _build_type_history(historical_claims, historical_eobs)

    # Build EOB lookup for target claims
    eob_by_claim = {}
    for eob in historical_eobs:
        ref = eob.get("claim", {}).get("reference", "")
        cid = ref.split("/")[-1] if "/" in ref else ref
        eob_by_claim[cid] = eob

    risk_counts = {"low": 0, "medium": 0, "high": 0}

    for claim in target_claims:
        claim_id = claim.get("id", "")
        claim_amount = float(claim.get("total", {}).get("value", 0))
        patient_ref = claim.get("patient", {}).get("reference", "")
        pid = patient_ref.split("/")[-1] if "/" in patient_ref else patient_id

        # Get claim type
        claim_type = "unknown"
        for coding in claim.get("type", {}).get("coding", []):
            claim_type = coding.get("code", "unknown")
            break

        # Get payer from corresponding EOB
        payer_name = "unknown"
        eob = eob_by_claim.get(claim_id)
        if eob:
            for ins in eob.get("insurance", []):
                payer_name = ins.get("coverage", {}).get("display",
                            ins.get("coverage", {}).get("reference", "unknown"))
                break

        risk_factors = []
        risk_score = 50.0  # Start neutral

        # Factor 1: Payer denial history
        payer = payer_history.get(payer_name, {})
        if payer.get("total", 0) > 0:
            payer_denial_rate = payer["denied"] / payer["total"]
            if payer_denial_rate > 0.3:
                risk_score += 20
                risk_factors.append(RiskFactor(
                    factor="Payer Denial History",
                    impact="negative",
                    detail=f"{payer_name} has {payer_denial_rate:.0%} denial rate",
                    weight=20.0,
                ))
            elif payer_denial_rate < 0.1:
                risk_score -= 15
                risk_factors.append(RiskFactor(
                    factor="Payer Denial History",
                    impact="positive",
                    detail=f"{payer_name} has low {payer_denial_rate:.0%} denial rate",
                    weight=-15.0,
                ))
            else:
                risk_factors.append(RiskFactor(
                    factor="Payer Denial History",
                    impact="neutral",
                    detail=f"{payer_name} has {payer_denial_rate:.0%} denial rate",
                    weight=0.0,
                ))

        # Factor 2: Claim amount (high-value claims have higher risk)
        if claim_amount > 10000:
            risk_score += 15
            risk_factors.append(RiskFactor(
                factor="High-Value Claim",
                impact="negative",
                detail=f"${claim_amount:,.2f} exceeds $10K threshold",
                weight=15.0,
            ))
        elif claim_amount < 500:
            risk_score -= 10
            risk_factors.append(RiskFactor(
                factor="Low-Value Claim",
                impact="positive",
                detail=f"${claim_amount:,.2f} is below $500 — typically auto-adjudicated",
                weight=-10.0,
            ))

        # Factor 3: Claim type history
        type_data = type_history.get(claim_type, {})
        if type_data.get("total", 0) > 5:
            type_denial_rate = type_data["denied"] / type_data["total"]
            if type_denial_rate > 0.25:
                risk_score += 10
                risk_factors.append(RiskFactor(
                    factor="Claim Type Risk",
                    impact="negative",
                    detail=f"'{claim_type}' claims have {type_denial_rate:.0%} denial rate",
                    weight=10.0,
                ))

        # Factor 4: Claim age
        claim_date = claim.get("created", "")
        if claim_date:
            try:
                from datetime import datetime
                cd = datetime.fromisoformat(claim_date[:10])
                age_days = (datetime.now() - cd).days
                if age_days > 90:
                    risk_score += 10
                    risk_factors.append(RiskFactor(
                        factor="Aging Claim",
                        impact="negative",
                        detail=f"Claim is {age_days} days old — payment likelihood decreases with age",
                        weight=10.0,
                    ))
            except (ValueError, TypeError):
                pass

        # Clamp risk score
        risk_score = max(0, min(100, risk_score))

        # Determine risk level
        if risk_score >= 70:
            risk_level = "high"
        elif risk_score >= 40:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Predict payment
        payment_probability = max(0, min(1.0, 1.0 - (risk_score / 100)))
        predicted_payment = claim_amount * payment_probability

        # Recommendation
        if risk_level == "high":
            rec = f"High risk (score {risk_score:.0f}). Proactively verify eligibility and authorization before submission. Consider pre-authorization."
        elif risk_level == "medium":
            rec = f"Moderate risk (score {risk_score:.0f}). Ensure clean claim submission with complete documentation."
        else:
            rec = f"Low risk (score {risk_score:.0f}). Standard submission expected to process normally."

        prediction = PaymentPrediction(
            claim_id=claim_id,
            patient_id=pid,
            claim_amount=claim_amount,
            predicted_payment=round(predicted_payment, 2),
            payment_probability=round(payment_probability, 3),
            risk_level=risk_level,
            risk_score=round(risk_score, 1),
            risk_factors=risk_factors,
            recommendation=rec,
        )

        report.predictions.append(prediction)
        risk_counts[risk_level] += 1

        if risk_level in ("high", "medium"):
            report.total_at_risk_amount += claim_amount

    report.total_claims_analyzed = len(target_claims)
    report.risk_distribution = risk_counts

    if report.predictions:
        report.portfolio_risk_score = round(
            sum(p.risk_score for p in report.predictions) / len(report.predictions), 1
        )

    return report
