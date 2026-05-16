# HealthPay GCP

AI-powered healthcare payment reconciliation agent built on MongoDB Atlas + Google Cloud Agent Builder + Gemini.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Database | MongoDB Atlas (FHIR claims, EOBs, patients) |
| AI / LLM | Gemini 1.5 Pro via Google Cloud Vertex AI |
| Agent Framework | Google Cloud Agent Builder |
| Data | Synthea synthetic FHIR R4 bundles |
| Language | Python 3.11+ |

## Quick Start

**1. Clone and install dependencies**
```bash
cd /home/taomi/projects/healthpay-gcp
pip install -r requirements.txt
```

**2. Configure environment**
```bash
cp .env.example .env
# Edit .env — set MONGODB_URI and GOOGLE_CLOUD_PROJECT
```

**3. Import FHIR data and run tests**
```bash
# Dry-run import (no DB writes)
python scripts/import_fhir_to_mongo.py --dry-run

# Real import (requires MONGODB_URI in .env)
python scripts/import_fhir_to_mongo.py --limit 100

# Run tests (mock mode, no DB needed)
python -m pytest tests/ -v
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MONGODB_URI` | Yes (for real data) | MongoDB Atlas connection string |
| `MONGODB_DB` | No | Database name (default: `healthpay`) |
| `GOOGLE_CLOUD_PROJECT` | Yes (for AI) | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | No | GCP region (default: `us-central1`) |
| `GEMINI_MODEL` | No | Gemini model name (default: `gemini-1.5-pro`) |

> **Note:** If `MONGODB_URI` is not set, the client runs in **mock mode** — all read methods return empty lists and writes are silently skipped. This allows development and testing without a live Atlas cluster.

## Project Structure

```
healthpay-gcp/
├── src/
│   ├── mongodb_client.py       # Atlas client with mock fallback
│   ├── data_importer.py        # Programmatic FHIR → MongoDB importer
│   ├── reconciliation_engine.py
│   ├── denial_analyzer.py
│   ├── risk_predictor.py
│   └── coding_optimizer.py
├── scripts/
│   └── import_fhir_to_mongo.py # CLI import tool
├── tests/
│   └── test_mongodb_client.py  # Unit tests (mock mode)
├── synthea/                    # Synthea FHIR test data
├── requirements.txt
├── .env.example
└── README.md
```

## Hackathon

Google Cloud Rapid Agent Hackathon — MongoDB Track ($5K prize, deadline 2025-06-11).

---

## Hackathon Submission

**Google Cloud Rapid Agent Hackathon — MongoDB Track**
Prize pool: $10K ($5K / $3K / $2K) | Deadline: June 12, 2026
Platform: https://rapid-agent.devpost.com/

### Project Highlights

| Highlight | Detail |
|-----------|--------|
| 5 MCP Tools | `reconcile_claims`, `analyze_denials`, `get_financial_vitals`, `predict_payment_risk`, `suggest_coding_optimization` |
| MongoDB Atlas | Persistent memory layer — stores FHIR claims, EOBs, denial history; vector search for similar claim patterns |
| Gemini Function Calling | Gemini 1.5 Pro drives multi-step RCM workflows via structured tool calls |
| Zero-key Demo | Full standalone demo runs without any API key (`python scripts/demo_standalone.py`) |
| Test Coverage | 35/35 tests passing in mock mode |

### Judging Criteria Alignment

| Criterion | How We Address It |
|-----------|-------------------|
| **Technological Implementation** | MongoDB Atlas as AI agent memory + vector search; Gemini function calling; MCP protocol for tool orchestration; Google Cloud Agent Builder integration |
| **Design** | Clean MCP tool interface; FHIR R4 data model; mock/real mode separation; modular src/ architecture |
| **Potential Impact** | 30%+ claim denial rate costs US healthcare $262B/year; this agent automates RCM for small-to-mid clinics that can't afford enterprise platforms |
| **Quality of Idea** | First open-source AI agent combining MongoDB Atlas vector search + Gemini + MCP for healthcare payment reconciliation |

### License

This project is licensed under the [MIT License](LICENSE).
