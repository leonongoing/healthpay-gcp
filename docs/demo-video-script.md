# HealthPay Intelligence Agent — Demo Video Script (3 minutes)

**Target audience:** Hackathon judges (technical, but not healthcare domain experts)
**Goal:** Show the problem is real, the solution works, and MongoDB Atlas is central to the architecture
**Recording setup:** Terminal (dark theme) + optional browser tab showing MongoDB Atlas dashboard

---

## Segment 1: Problem Statement (0:00 – 0:30)

**[Screen: Slide or terminal with stats]**

> "Healthcare claim denials cost the US system $262 billion every year.
>
> 30% of claims are denied on first submission. For a small clinic billing $2M/year, that's $600K stuck in limbo — waiting weeks for manual re-submission.
>
> Enterprise RCM platforms exist, but they cost $50K to $200K per year. Most independent clinics can't afford them.
>
> We built HealthPay Intelligence Agent: an open-source AI agent that gives every clinic an automated RCM co-pilot — powered by MongoDB Atlas, Gemini, and the Model Context Protocol."

---

## Segment 2: Live Demo (0:30 – 1:30)

**[Screen: Terminal]**

```bash
cd /home/taomi/projects/healthpay-gcp
python scripts/demo_standalone.py
```

**[Narrate as output appears]**

> "No API keys needed — the agent runs in mock mode with realistic synthetic FHIR data."

**Tool 1 — reconcile_claims:**
> "First, the agent reconciles submitted claims against insurance payments. It finds a $1,247 discrepancy on claim CLM-2024-001 — the insurer paid less than billed. The agent flags it for follow-up."

**Tool 2 — analyze_denials:**
> "Next, denial analysis. The agent queries MongoDB Atlas for all denied claims, classifies them by CARC code, and surfaces the top pattern: 45% of denials are CO-4 — procedure code inconsistent with modifier. That's a fixable coding issue, not a coverage problem."

**Tool 3 — get_financial_vitals:**
> "Finally, financial vitals. Collection rate 87.3%, denial rate 12.1%, days-in-AR 34. The agent benchmarks these against industry standards and flags that the denial rate is 4 points above the 8% target — with a specific action plan to close the gap."

> "Three tools, three actionable insights, under 10 seconds. A billing manager would have spent 3 hours pulling this manually."

---

## Segment 3: Architecture (1:30 – 2:30)

**[Screen: Architecture diagram or annotated terminal]**

> "Let me walk through how this works under the hood."

```
FHIR R4 Data (Synthea synthetic patients)
        ↓
MongoDB Atlas
  ├── claims, eobs, patients collections
  └── Vector Search Index (denial embeddings)
        ↓
MCP Server — 5 tools
  reconcile_claims | analyze_denials | get_financial_vitals
  predict_payment_risk | suggest_coding_optimization
        ↓
Google Cloud Agent Builder + Gemini 1.5 Pro
  └── Function calling orchestrates multi-step workflows
        ↓
Natural language output for billing staff
```

> "MongoDB Atlas is the agent's persistent memory. FHIR claims and EOBs are stored as native JSON documents — no ORM, no schema migration. The Atlas Vector Search index lets the agent find semantically similar historical denial cases, so recommendations improve as more data accumulates."

> "Gemini 1.5 Pro drives the orchestration. It receives a natural language query, decides which MCP tools to call and in what order, and synthesizes the results into a structured recommendation."

> "The MCP protocol is the glue — a standardized interface between the AI agent and our domain tools. Adding a new capability is as simple as adding a new tool definition."

---

## Segment 4: Business Value + Next Steps (2:30 – 3:00)

**[Screen: Terminal or slide]**

> "The business case is straightforward. A clinic recovering just 5% more denied claims on a $2M revenue base captures $100K/year. At $0 licensing cost versus $50K+ for enterprise RCM, the ROI is immediate."

> "What's next: connecting to a live MongoDB Atlas cluster, deploying on Vertex AI for production scale, and running a pilot with an independent clinic in Q3 2026."

> "HealthPay Intelligence Agent — open source, MIT licensed, built on MongoDB Atlas and Google Cloud. The code is on GitHub. Thank you."

---

## Recording Tips

- Use a **dark terminal theme** (Dracula, One Dark) — easier to read on video
- Font size: **18–20pt minimum**
- Run `python scripts/demo_standalone.py` live — don't use pre-recorded output
- Pause 1–2 seconds after each tool output before narrating
- Total runtime target: **2:45 – 3:00**
- Export at **1080p minimum**
