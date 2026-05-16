#!/usr/bin/env python3
"""
HealthPay Intelligence Agent — Standalone Demo
Runs without any API keys or database connections.
Shows the full agent capability with realistic mock data.

Usage:
    python scripts/demo_standalone.py
    python scripts/demo_standalone.py --interactive
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
import random

# ─── ANSI colors ──────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"
RED    = "\033[31m"
BLUE   = "\033[34m"
GRAY   = "\033[90m"

def c(color, text): return f"{color}{text}{RESET}"
def header(text): print(f"\n{BOLD}{CYAN}{'='*60}{RESET}\n{BOLD}{CYAN}  {text}{RESET}\n{BOLD}{CYAN}{'='*60}{RESET}")
def subheader(text): print(f"\n{BOLD}{YELLOW}▶ {text}{RESET}")
def thinking(text): print(f"{GRAY}  [Agent thinking] {text}...{RESET}"); time.sleep(0.4)
def tool_call(name, args=""): print(f"{BLUE}  → Calling tool: {BOLD}{name}{RESET}{BLUE}({args}){RESET}"); time.sleep(0.3)
def result_line(text): print(f"{GREEN}  ✓ {text}{RESET}")
def warn_line(text): print(f"{YELLOW}  ⚠ {text}{RESET}")
def error_line(text): print(f"{RED}  ✗ {text}{RESET}")

# ─── Mock data ────────────────────────────────────────────────────────────────

MOCK_RECONCILIATION = {
    "total_claims": 247,
    "matched": 198,
    "discrepancies": 31,
    "unmatched": 18,
    "total_billed": 1_284_500.00,
    "total_paid": 892_340.00,
    "total_discrepancy_amount": 127_890.00,
    "match_rate": 80.2,
    "top_discrepancies": [
        {"claim_id": "C-2024-0891", "patient": "Sarah Johnson", "billed": 4200.00, "paid": 2100.00, "delta": -2100.00, "reason": "Bundling — procedure codes 99213+99214 bundled by payer"},
        {"claim_id": "C-2024-1023", "patient": "Michael Chen",  "billed": 8750.00, "paid": 0.00,    "delta": -8750.00, "reason": "Denial — CO-4: Modifier required but not provided"},
        {"claim_id": "C-2024-0756", "patient": "Emma Williams", "billed": 1850.00, "paid": 925.00,  "delta": -925.00,  "reason": "Coordination of benefits — secondary payer not billed"},
        {"claim_id": "C-2024-1187", "patient": "James Rodriguez","billed": 3300.00, "paid": 2640.00, "delta": -660.00,  "reason": "Contractual adjustment — rate differs from fee schedule"},
        {"claim_id": "C-2024-0934", "patient": "Lisa Park",     "billed": 6100.00, "paid": 0.00,    "delta": -6100.00, "reason": "Denial — CO-97: Payment included in allowance for another service"},
    ],
    "ai_summary": (
        "Reconciliation complete. 80.2% match rate across 247 claims. "
        "Critical finding: $127,890 in discrepancies — top issues are modifier errors (CO-4) "
        "and bundling disputes. Recommend immediate appeal on C-2024-1023 and C-2024-0934 "
        "(combined $14,850 recovery potential). Modifier training for billing staff would "
        "prevent ~40% of future denials."
    )
}

MOCK_DENIALS = {
    "total_eobs_analyzed": 89,
    "total_denials": 31,
    "denial_rate": 34.8,
    "total_denied_amount": 127_890.00,
    "appealable_amount": 94_230.00,
    "appeal_success_rate_estimate": 0.38,
    "estimated_recovery": 35_807.00,
    "top_denial_reasons": [
        {"carc_code": "CO-4",  "description": "Modifier required but not provided",          "count": 9,  "amount": 42_100.00, "appealable": True,  "strategy": "Append modifier -25 or -59 and resubmit within 90 days"},
        {"carc_code": "CO-97", "description": "Payment included in allowance for another service", "count": 7, "amount": 38_200.00, "appealable": True,  "strategy": "Unbundle services and submit with supporting documentation"},
        {"carc_code": "CO-16", "description": "Claim lacks information needed for adjudication", "count": 6, "amount": 21_400.00, "appealable": True,  "strategy": "Resubmit with complete patient demographics and NPI"},
        {"carc_code": "CO-50", "description": "Non-covered service",                          "count": 5,  "amount": 15_890.00, "appealable": False, "strategy": "Bill patient directly or write off"},
        {"carc_code": "CO-22", "description": "Coordination of benefits",                     "count": 4,  "amount": 10_300.00, "appealable": True,  "strategy": "Verify primary/secondary payer order and resubmit"},
    ],
    "payer_breakdown": [
        {"payer": "Aetna",    "denials": 12, "amount": 54_200.00, "denial_rate": "38%"},
        {"payer": "UnitedHC", "denials": 9,  "amount": 41_100.00, "denial_rate": "31%"},
        {"payer": "BCBS",     "denials": 7,  "amount": 22_390.00, "denial_rate": "28%"},
        {"payer": "Cigna",    "denials": 3,  "amount": 10_200.00, "denial_rate": "22%"},
    ]
}

MOCK_FINANCIAL_VITALS = {
    "report_date": datetime.now().strftime("%Y-%m-%d"),
    "total_ar": 892_340.00,
    "collection_rate": 69.5,
    "days_in_ar": 42.3,
    "ar_aging": {
        "0_30_days":   {"amount": 312_400.00, "pct": 35.0},
        "31_60_days":  {"amount": 267_800.00, "pct": 30.0},
        "61_90_days":  {"amount": 178_500.00, "pct": 20.0},
        "91_120_days": {"amount": 89_200.00,  "pct": 10.0},
        "over_120":    {"amount": 44_440.00,  "pct": 5.0},
    },
    "payer_performance": [
        {"payer": "Medicare",  "avg_days_to_pay": 14, "collection_rate": "94%", "denial_rate": "8%",  "grade": "A"},
        {"payer": "Medicaid",  "avg_days_to_pay": 28, "collection_rate": "81%", "denial_rate": "15%", "grade": "B"},
        {"payer": "BCBS",      "avg_days_to_pay": 21, "collection_rate": "88%", "denial_rate": "12%", "grade": "B+"},
        {"payer": "Aetna",     "avg_days_to_pay": 35, "collection_rate": "72%", "denial_rate": "22%", "grade": "C"},
        {"payer": "UnitedHC",  "avg_days_to_pay": 31, "collection_rate": "76%", "denial_rate": "18%", "grade": "C+"},
    ],
    "alerts": [
        "⚠ A/R over 90 days: $133,640 (15%) — exceeds 10% benchmark",
        "⚠ Aetna denial rate 22% — above 15% threshold, review modifier usage",
        "✓ Medicare performance excellent — 14-day avg payment, 94% collection",
    ]
}

MOCK_RISK_PREDICTION = {
    "claim_id": "C-2024-1234",
    "patient_id": "P-0891",
    "risk_score": 0.73,
    "risk_level": "HIGH",
    "predicted_outcome": "Likely denial or significant reduction",
    "risk_factors": [
        {"factor": "Missing modifier on CPT 99214",          "weight": 0.35, "impact": "HIGH"},
        {"factor": "Aetna payer — 22% historical denial rate","weight": 0.25, "impact": "MEDIUM"},
        {"factor": "Diagnosis-procedure mismatch (ICD-10)",  "weight": 0.13, "impact": "MEDIUM"},
    ],
    "recommendations": [
        "Add modifier -25 to CPT 99214 before submission",
        "Verify ICD-10 code Z00.00 supports the procedure",
        "Consider pre-authorization for this payer/procedure combination",
    ],
    "estimated_payment_if_submitted_now": 0.00,
    "estimated_payment_after_fixes": 3_200.00,
}

MOCK_CODING_OPTIMIZATION = {
    "claims_analyzed": 50,
    "issues_found": 14,
    "estimated_revenue_impact": 67_400.00,
    "top_issues": [
        {"issue": "Upcoding risk: CPT 99215 used for 15-min visits (should be 99213)", "count": 6, "risk": "HIGH",   "action": "Downcode to 99213 — reduces audit risk"},
        {"issue": "Missing modifier -25 on E&M + procedure same day",                  "count": 5, "risk": "HIGH",   "action": "Add modifier -25 to E&M code"},
        {"issue": "ICD-10 specificity: using Z00.00 instead of Z00.01",               "count": 3, "risk": "MEDIUM", "action": "Use Z00.01 for routine child health exam"},
    ]
}

# ─── Demo scenarios ───────────────────────────────────────────────────────────

def demo_reconciliation():
    subheader("Query 1: Reconcile all claims and show discrepancies")
    print(f"  {BOLD}User:{RESET} Reconcile all claims for this month and show me the top discrepancies")
    print()
    thinking("Analyzing 247 claims against EOBs in MongoDB Atlas")
    tool_call("reconcile_claims", "limit=247")
    thinking("Identifying discrepancies and calculating recovery potential")
    print()

    d = MOCK_RECONCILIATION
    print(f"  {BOLD}Agent:{RESET}")
    print(f"  Reconciliation complete for {d['total_claims']} claims:")
    print()
    print(f"    {'Matched:':<25} {c(GREEN, str(d['matched']))} ({d['match_rate']}% match rate)")
    print(f"    {'Discrepancies:':<25} {c(YELLOW, str(d['discrepancies']))}")
    print(f"    {'Unmatched:':<25} {c(RED, str(d['unmatched']))}")
    print(f"    {'Total billed:':<25} ${d['total_billed']:,.2f}")
    print(f"    {'Total paid:':<25} ${d['total_paid']:,.2f}")
    print(f"    {'Discrepancy amount:':<25} {c(RED, f'${d["total_discrepancy_amount"]:,.2f}')}")
    print()
    print(f"  {BOLD}Top 5 discrepancies:{RESET}")
    for item in d["top_discrepancies"]:
        delta_str = c(RED, f"${item['delta']:,.2f}")
        print(f"    • {item['claim_id']} ({item['patient']}): {delta_str}")
        print(f"      {GRAY}{item['reason']}{RESET}")
    print()
    print(f"  {BOLD}AI Summary:{RESET} {d['ai_summary']}")

def demo_denial_analysis():
    subheader("Query 2: Analyze denials and suggest appeal strategies")
    print(f"  {BOLD}User:{RESET} What are our top denial reasons and what should we appeal first?")
    print()
    thinking("Querying MongoDB Atlas for EOBs with denial codes")
    tool_call("analyze_denials", "limit=89")
    thinking("Classifying CARC codes and calculating appeal ROI")
    print()

    d = MOCK_DENIALS
    print(f"  {BOLD}Agent:{RESET}")
    print(f"  Denial analysis complete — {d['total_denials']} denials across {d['total_eobs_analyzed']} EOBs:")
    print()
    print(f"    {'Denial rate:':<30} {c(RED, f'{d["denial_rate"]}%')} (benchmark: <15%)")
    print(f"    {'Total denied:':<30} ${d['total_denied_amount']:,.2f}")
    print(f"    {'Appealable amount:':<30} {c(GREEN, f'${d["appealable_amount"]:,.2f}')}")
    print(f"    {'Estimated recovery (38%):':<30} {c(GREEN, f'${d["estimated_recovery"]:,.2f}')}")
    print()
    print(f"  {BOLD}Top denial reasons (prioritized by appeal ROI):{RESET}")
    for item in d["top_denial_reasons"]:
        appealable = c(GREEN, "✓ Appealable") if item["appealable"] else c(RED, "✗ Write-off")
        print(f"    • {c(BOLD, item['carc_code'])}: {item['description']}")
        print(f"      Count: {item['count']} | Amount: ${item['amount']:,.2f} | {appealable}")
        print(f"      {GRAY}Strategy: {item['strategy']}{RESET}")
    print()
    print(f"  {BOLD}Payer breakdown:{RESET}")
    for p in d["payer_breakdown"]:
        print(f"    • {p['payer']:<12} {p['denials']} denials | ${p['amount']:,.2f} | {p['denial_rate']} denial rate")

def demo_financial_vitals():
    subheader("Query 3: Financial health dashboard")
    print(f"  {BOLD}User:{RESET} Show me our A/R aging and which payers are performing worst")
    print()
    thinking("Aggregating A/R aging buckets from MongoDB")
    tool_call("get_financial_vitals")
    print()

    d = MOCK_FINANCIAL_VITALS
    print(f"  {BOLD}Agent:{RESET}")
    print(f"  Financial vitals as of {d['report_date']}:")
    print()
    print(f"    {'Total A/R:':<30} ${d['total_ar']:,.2f}")
    print(f"    {'Collection rate:':<30} {d['collection_rate']}% (benchmark: 95%+)")
    print(f"    {'Days in A/R:':<30} {d['days_in_ar']} days (benchmark: <30)")
    print()
    print(f"  {BOLD}A/R Aging Buckets:{RESET}")
    for bucket, data in d["ar_aging"].items():
        bar_len = int(data["pct"] / 2)
        bar = "█" * bar_len
        color = GREEN if bucket == "0_30_days" else (YELLOW if bucket in ["31_60_days", "61_90_days"] else RED)
        label = bucket.replace("_", " ").replace("days", "d")
        print(f"    {label:<15} {c(color, bar):<30} ${data['amount']:>12,.2f} ({data['pct']}%)")
    print()
    print(f"  {BOLD}Payer Performance:{RESET}")
    for p in d["payer_performance"]:
        grade_color = GREEN if p["grade"].startswith("A") else (YELLOW if p["grade"].startswith("B") else RED)
        print(f"    • {p['payer']:<12} Grade: {c(grade_color, p['grade'])} | {p['avg_days_to_pay']}d avg | {p['collection_rate']} collected | {p['denial_rate']} denied")
    print()
    print(f"  {BOLD}Alerts:{RESET}")
    for alert in d["alerts"]:
        print(f"    {alert}")

def demo_risk_prediction():
    subheader("Query 4: Pre-submission risk scoring")
    print(f"  {BOLD}User:{RESET} Score claim C-2024-1234 before I submit it — is it likely to be denied?")
    print()
    thinking("Loading claim C-2024-1234 from MongoDB")
    tool_call("predict_payment_risk", "claim_id='C-2024-1234'")
    thinking("Running risk model against historical payer patterns")
    print()

    d = MOCK_RISK_PREDICTION
    risk_color = RED if d["risk_level"] == "HIGH" else (YELLOW if d["risk_level"] == "MEDIUM" else GREEN)
    print(f"  {BOLD}Agent:{RESET}")
    print(f"  Risk assessment for {d['claim_id']}:")
    print()
    print(f"    {'Risk score:':<30} {c(risk_color, f'{d["risk_score"]*100:.0f}/100')} — {c(risk_color, d['risk_level'])}")
    print(f"    {'Predicted outcome:':<30} {d['predicted_outcome']}")
    print(f"    {'Expected payment (now):':<30} {c(RED, f'${d["estimated_payment_if_submitted_now"]:,.2f}')}")
    print(f"    {'Expected payment (fixed):':<30} {c(GREEN, f'${d["estimated_payment_after_fixes"]:,.2f}')}")
    print()
    print(f"  {BOLD}Risk factors:{RESET}")
    for rf in d["risk_factors"]:
        impact_color = RED if rf["impact"] == "HIGH" else YELLOW
        print(f"    • {rf['factor']}")
        print(f"      Weight: {rf['weight']*100:.0f}% | Impact: {c(impact_color, rf['impact'])}")
    print()
    print(f"  {BOLD}Recommendations (fix before submitting):{RESET}")
    for i, rec in enumerate(d["recommendations"], 1):
        print(f"    {i}. {rec}")

# ─── Main ─────────────────────────────────────────────────────────────────────

def run_full_demo():
    header("HealthPay Intelligence Agent — Live Demo")
    print(f"  {BOLD}Powered by:{RESET} Gemini 3 (gemini-2.5-pro) + MongoDB Atlas + MCP")
    print(f"  {BOLD}Use case:{RESET} AI-powered healthcare payment reconciliation")
    print(f"  {BOLD}Problem:{RESET} US healthcare loses $262B/year to claim denials and payment errors")
    print()
    print(f"  {GRAY}Note: This demo uses realistic synthetic data (FHIR R4 format).{RESET}")
    print(f"  {GRAY}In production, data comes from MongoDB Atlas with real claims.{RESET}")

    time.sleep(0.5)
    demo_reconciliation()
    time.sleep(0.5)
    demo_denial_analysis()
    time.sleep(0.5)
    demo_financial_vitals()
    time.sleep(0.5)
    demo_risk_prediction()

    header("Demo Complete")
    print(f"  {BOLD}Impact summary:{RESET}")
    print(f"    • {c(GREEN, '$35,807')} estimated recovery from appeals (38% success rate)")
    print(f"    • {c(GREEN, '$3,200')} saved on claim C-2024-1234 by fixing before submission")
    print(f"    • {c(YELLOW, '14 coding issues')} identified — $67,400 revenue impact")
    print(f"    • {c(RED, '42.3 days')} in A/R → target: <30 days")
    print()
    print(f"  {BOLD}At scale:{RESET} 10,000 practices × $35K recovery = {c(GREEN, '$350M/year')}")
    print()
    print(f"  {GRAY}Built for Google Cloud Rapid Agent Hackathon | MongoDB Partner Track{RESET}")
    print(f"  {GRAY}Tech: Gemini 3 + Google Cloud Agent Builder + MongoDB Atlas + MCP{RESET}")
    print()

def run_interactive():
    header("HealthPay Intelligence Agent — Interactive Mode")
    print(f"  Type your question or 'quit' to exit.")
    print(f"  Example queries:")
    print(f"    - reconcile claims for patient P001")
    print(f"    - analyze denials and suggest appeals")
    print(f"    - show financial vitals")
    print(f"    - score claim C-2024-1234 for risk")
    print()

    while True:
        try:
            user_input = input(f"{BOLD}You:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input or user_input.lower() in ("quit", "exit", "q"):
            break

        msg = user_input.lower()
        print()
        if "reconcil" in msg:
            demo_reconciliation()
        elif "denial" in msg or "appeal" in msg:
            demo_denial_analysis()
        elif "financial" in msg or "vital" in msg or "aging" in msg or "ar" in msg:
            demo_financial_vitals()
        elif "risk" in msg or "score" in msg or "predict" in msg:
            demo_risk_prediction()
        else:
            print(f"  {BOLD}Agent:{RESET} I can help with: claim reconciliation, denial analysis,")
            print(f"  financial vitals, and payment risk prediction.")
            print(f"  Try: 'reconcile claims', 'analyze denials', 'show financial vitals', or 'score claim'")
        print()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HealthPay Agent Demo")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run in interactive mode")
    args = parser.parse_args()

    if args.interactive:
        run_interactive()
    else:
        run_full_demo()
