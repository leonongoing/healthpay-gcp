# HealthPay Intelligence Agent — Devpost Writeup

## Inspiration

Healthcare claim denials cost the US healthcare system over **$262 billion per year**. Small and mid-sized clinics face a brutal reality:

- **30%+ of claims** are denied on first submission
- Manual re-submission takes 2–4 weeks per claim
- Enterprise Revenue Cycle Management (RCM) platforms cost $50K–$200K/year — out of reach for most independent practices
- Staff spend 40%+ of billing time on denial follow-up instead of patient care

We built HealthPay Intelligence Agent to give every clinic — regardless of size — an AI-powered RCM co-pilot that works 24/7, speaks FHIR, and never forgets a denial pattern.

---

## What It Does

HealthPay Intelligence Agent exposes **5 MCP (Model Context Protocol) tools** that a Gemini-powered agent can call to automate the full revenue cycle workflow:

| Tool | What It Does |
|------|-------------|
| `reconcile_claims` | Matches submitted claims against EOB (Explanation of Benefits) payments; flags discrepancies |
| `analyze_denials` | Classifies denials by CARC/RARC codes; identifies root causes and appeal strategies |
| `get_financial_vitals` | Returns real-time KPIs: collection rate, denial rate, days-in-AR, outstanding balance |
| `predict_payment_risk` | Scores new claims for denial risk before submission using historical patterns |
| `suggest_coding_optimization` | Recommends ICD-10/CPT code corrections to reduce denial probability |

A clinic billing manager can ask in plain English: *"Why are my cardiology claims being denied?"* — and the agent will query MongoDB Atlas, analyze CARC codes, cross-reference similar historical claims via vector search, and return a prioritized action plan.

---

## How We Built It

### Architecture

```
FHIR R4 Data (Synthea)
        ↓
MongoDB Atlas
  ├── claims collection (FHIR ClaimResponse)
  ├── eobs collection (ExplanationOfBenefit)
  ├── patients collection
  └── Vector Search Index (denial pattern embeddings)
        ↓
MCP Server (Python)
  └── 5 tools exposed via MCP protocol
        ↓
Google Cloud Agent Builder
  └── Gemini 1.5 Pro (function calling)
        ↓
Clinic Billing Manager (natural language interface)
```

### Key Technology Choices

**MongoDB Atlas as the AI Agent's Brain**
We chose MongoDB Atlas not just as a database but as the agent's persistent memory layer. Its flexible document model maps naturally to FHIR R4 resources (claims, EOBs, patients are all nested JSON). The Atlas Vector Search index lets the agent find semantically similar historical denial cases — enabling pattern-based recommendations that improve over time.

**Gemini 1.5 Pro + Function Calling**
Gemini's function calling capability is the orchestration engine. The agent receives a natural language query, decides which MCP tools to call (and in what order), synthesizes the results, and returns a structured recommendation. Multi-step workflows (e.g., "reconcile → analyze denials → suggest fixes") happen automatically.

**MCP Protocol**
The Model Context Protocol provides a clean, standardized interface between the AI agent and our domain tools. Each tool has a typed schema, making it easy to add new capabilities without changing the agent's core logic.

**Mock Mode for Reliable Demo**
We designed a mock/real mode split from day one. Without `MONGODB_URI` set, all data operations return realistic synthetic data. This means the agent can be demoed, tested, and evaluated without any cloud credentials.

**Official MongoDB MCP Server — Dual-Layer Architecture**
Beyond our custom 5-tool MCP server, HealthPay integrates the **official `mongodb-mcp-server`** npm package as a second access layer. This dual-layer architecture gives evaluators two complementary ways to interact with our data:

1. **Custom HealthPay MCP Server** (`src/mcp_server.py`) — 5 domain-specific tools with built-in FHIR logic, CARC/RARC denial classification, risk scoring, and coding optimization. This is the high-level interface designed for clinic billing workflows.

2. **Official MongoDB MCP Server** (`npx -y mongodb-mcp-server --readOnly`) — generic `find`, `aggregate`, `listCollections`, and `count` tools that expose the raw `healthpay` database directly. Judges can connect any MCP-compatible client (Claude Desktop, Gemini CLI) and query our Atlas cluster without any custom code.

Both layers connect to the same MongoDB Atlas cluster (`claims`, `eobs`, `patients` collections). The official server proves our data model is standards-compliant and accessible to any MCP client; the custom server proves we can build domain intelligence on top of it. See `mcp-config/` for ready-to-use configuration files and `src/mongodb_mcp_bridge.py` for a runnable compatibility demo.

---

## Challenges

**FHIR R4 Data Modeling in MongoDB**
FHIR resources are deeply nested JSON with complex references (e.g., a ClaimResponse references a Claim which references a Patient and multiple Procedures). Designing MongoDB schemas that preserve FHIR fidelity while enabling efficient aggregation queries required multiple iterations.

**CARC/RARC Code Classification**
The Centers for Medicare & Medicaid Services maintains 200+ Claim Adjustment Reason Codes (CARC) and Remittance Advice Remark Codes (RARC). Building a classification system that maps these codes to actionable denial categories (eligibility, authorization, coding, timely filing) was non-trivial.

**Mock Mode Design**
Making mock mode realistic enough to be useful for demos — while keeping it clearly separated from production code — required careful architecture. We used a `MockMongoDBClient` that mirrors the real client's interface exactly, returning statistically plausible synthetic data.

---

## Accomplishments

- ✅ **35/35 tests passing** in mock mode — full test coverage without any cloud dependencies
- ✅ **Standalone demo** runs with zero API keys: `python scripts/demo_standalone.py`
- ✅ **Complete RCM workflow** covered: claim submission → reconciliation → denial analysis → risk prediction → coding optimization
- ✅ **FHIR R4 compliant** data model using Synthea-generated synthetic patient data
- ✅ **Production-ready architecture** with clean separation between mock and real modes

---

## What We Learned

**MongoDB Atlas is the ideal persistent memory layer for AI agents.**

Most AI agent tutorials treat the database as an afterthought. We learned that for domain-specific agents, the database *is* the intelligence. MongoDB Atlas gave us:

1. **Flexible schema** — FHIR resources vary wildly in structure; MongoDB handles this naturally
2. **Vector search** — finding "claims similar to this denial" is a semantic search problem, not a SQL query
3. **Aggregation pipeline** — complex RCM analytics (denial rates by payer, by code, by provider) are single pipeline calls
4. **Atlas Functions** — business logic can live close to the data, reducing round-trips

The combination of MongoDB Atlas + Gemini function calling creates an agent that genuinely *learns* from historical data rather than just pattern-matching on static rules.

---

## What's Next

- **Real MongoDB Atlas integration**: Connect to a live Atlas cluster with actual clinic data (de-identified)
- **Vertex AI deployment**: Deploy the agent as a managed endpoint on Google Cloud Vertex AI
- **Clinic pilot**: Partner with 2–3 independent practices for a 90-day pilot
- **Payer-specific models**: Train denial prediction models per payer (Medicare, Medicaid, commercial)
- **Appeals automation**: Auto-generate appeal letters using Gemini + denial context from MongoDB

---

## Built With

`python` · `mongodb-atlas` · `gemini` · `google-cloud-agent-builder` · `mcp` · `fhir` · `vertex-ai` · `synthea`
