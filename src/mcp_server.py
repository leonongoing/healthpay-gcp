"""
MCP Server for HealthPay GCP.
Exposes 5 healthcare payment intelligence tools via Model Context Protocol.
"""

import logging

logger = logging.getLogger(__name__)


def tool_reconcile_claims(patient_id=None, limit=100):
    """Reconcile claims against EOBs and identify discrepancies."""
    from src.mongodb_client import MongoDBClient
    from src.reconciliation_engine import reconcile_from_mongodb
    from src.gemini_client import GeminiClient

    db = MongoDBClient()
    gemini = GeminiClient()
    # signature: reconcile_from_mongodb(patient_id, mongodb_client, limit)
    result = reconcile_from_mongodb(patient_id, db, limit=limit)
    summary = result if isinstance(result, dict) else result.model_dump()
    ai_summary = gemini.summarize_reconciliation(summary)
    return {"result": summary, "ai_summary": ai_summary}


def tool_analyze_denials(patient_id=None, limit=50):
    """Analyze claim denials and suggest appeal strategies."""
    from src.mongodb_client import MongoDBClient
    from src.denial_analyzer import run_denial_analysis

    db = MongoDBClient()
    # signature: run_denial_analysis(patient_id, mongodb_client, limit)
    result = run_denial_analysis(patient_id, db, limit=limit)
    return result if isinstance(result, dict) else result.model_dump()


def tool_get_financial_vitals():
    """Return A/R aging, collection rates, and payer performance."""
    from src.financial_vitals import FinancialVitals

    vitals = FinancialVitals()
    report = vitals.get_full_report()
    return report if isinstance(report, dict) else report.model_dump()


def tool_predict_payment_risk(claim_id):
    """Score a claim by payment probability."""
    from src.mongodb_client import MongoDBClient
    from src.risk_predictor import predict_payment_risk

    db = MongoDBClient()
    claims = db.get_claims(limit=500)
    eobs = db.get_eobs(limit=500)
    claim = next((c for c in claims if c.get("id") == claim_id), None)
    if claim is None:
        return {"claim_id": claim_id, "error": "Claim not found (mock mode: no data)"}
    result = predict_payment_risk(claim, claims, eobs)
    return result if isinstance(result, dict) else result.model_dump()


def tool_suggest_coding_optimization(patient_id=None, limit=50):
    """Identify ICD-10/CPT coding issues that cause denials."""
    from src.mongodb_client import MongoDBClient
    from src.coding_optimizer import suggest_coding_optimization

    db = MongoDBClient()
    claims = db.get_claims(patient_id=patient_id, limit=limit)
    eobs = db.get_eobs(limit=limit)
    # signature: suggest_coding_optimization(patient_id, claims, eobs)
    result = suggest_coding_optimization(patient_id or "all", claims, eobs)
    return result if isinstance(result, dict) else result.model_dump()


TOOLS = {
    "reconcile_claims": {
        "fn": tool_reconcile_claims,
        "description": "Reconcile claims against EOBs and identify payment discrepancies",
        "parameters": {
            "patient_id": {"type": "string", "description": "Filter by patient ID (optional)"},
            "limit": {"type": "integer", "description": "Max claims to process (default 100)"},
        },
    },
    "analyze_denials": {
        "fn": tool_analyze_denials,
        "description": "Analyze claim denials, classify root causes, generate appeal strategies",
        "parameters": {
            "patient_id": {"type": "string", "description": "Filter by patient ID (optional)"},
            "limit": {"type": "integer", "description": "Max EOBs to analyze (default 50)"},
        },
    },
    "get_financial_vitals": {
        "fn": tool_get_financial_vitals,
        "description": "Return A/R aging dashboard, collection rates, and payer performance metrics",
        "parameters": {},
    },
    "predict_payment_risk": {
        "fn": tool_predict_payment_risk,
        "description": "Score a claim by payment probability before submission",
        "parameters": {
            "claim_id": {"type": "string", "description": "Claim ID to score (required)"},
        },
    },
    "suggest_coding_optimization": {
        "fn": tool_suggest_coding_optimization,
        "description": "Identify ICD-10/CPT coding issues that cause denials",
        "parameters": {
            "patient_id": {"type": "string", "description": "Filter by patient ID (optional)"},
            "limit": {"type": "integer", "description": "Max claims to analyze (default 50)"},
        },
    },
}


def list_tools():
    """Return MCP-compatible tool list."""
    return [
        {
            "name": name,
            "description": meta["description"],
            "inputSchema": {"type": "object", "properties": meta["parameters"]},
        }
        for name, meta in TOOLS.items()
    ]


def call_tool(name: str, arguments: dict):
    """Call a tool by name with given arguments."""
    if name not in TOOLS:
        raise ValueError(f"Unknown tool: {name}. Available: {list(TOOLS.keys())}")
    return TOOLS[name]["fn"](**arguments)
