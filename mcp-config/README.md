# MCP Configuration — Official MongoDB MCP Server

This directory contains configuration files for connecting to the HealthPay MongoDB Atlas cluster
using the **official `mongodb-mcp-server`** npm package.

## Prerequisites

- Node.js 18+ (for `npx`)
- A valid MongoDB Atlas connection string for the `healthpay` database

## Quick Setup

### 1. Get the connection string

Contact the project maintainer for the Atlas connection string, or set up your own Atlas cluster
and import data using `scripts/import_fhir_to_mongo.py`.

### 2. Replace the placeholder

In the config files below, replace:
```
mongodb+srv://USER:PASS@cluster.mongodb.net/healthpay
```
with your actual Atlas connection string.

---

## Claude Desktop

Copy the contents of `claude-desktop-config.json` into your Claude Desktop config file:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "mongodb-healthpay": {
      "command": "npx",
      "args": ["-y", "mongodb-mcp-server", "--readOnly"],
      "env": {
        "MDB_MCP_CONNECTION_STRING": "mongodb+srv://USER:PASS@cluster.mongodb.net/healthpay"
      }
    }
  }
}
```

After saving, restart Claude Desktop. You'll see `mongodb-healthpay` in the MCP tools panel.

---

## Gemini CLI (GCP Rapid Agent)

Copy `gemini-cli-config.json` to your Gemini CLI settings directory, or pass it via the
`--mcp-config` flag:

```bash
export MDB_MCP_CONNECTION_STRING="mongodb+srv://USER:PASS@cluster.mongodb.net/healthpay"
gemini --mcp-config mcp-config/gemini-cli-config.json
```

Or set the environment variable and run the MCP server directly:

```bash
export MDB_MCP_CONNECTION_STRING="mongodb+srv://USER:PASS@cluster.mongodb.net/healthpay"
npx -y mongodb-mcp-server --readOnly
```

---

## Available Tools (read-only mode)

| Tool | Description |
|------|-------------|
| `find` | Query documents in any collection |
| `aggregate` | Run aggregation pipelines |
| `listCollections` | List all collections in the database |
| `listDatabases` | List all accessible databases |
| `count` | Count documents matching a filter |
| `distinct` | Get distinct values for a field |

## HealthPay Collections

| Collection | Contents |
|------------|----------|
| `claims` | FHIR R4 ClaimResponse documents |
| `eobs` | FHIR R4 ExplanationOfBenefit documents |
| `patients` | FHIR R4 Patient demographics |

## Example Queries via MCP

**List all collections:**
```
Use the listCollections tool on database "healthpay"
```

**Find denied claims:**
```
Use the find tool: collection="claims", database="healthpay",
filter={"outcome": "denied"}, limit=10
```

**Denial rate by payer (aggregation):**
```
Use the aggregate tool: collection="claims", database="healthpay",
pipeline=[
  {"$group": {"_id": "$insurer.display", "total": {"$sum": 1},
              "denied": {"$sum": {"$cond": [{"$eq": ["$outcome","denied"]}, 1, 0]}}}},
  {"$addFields": {"denial_rate": {"$divide": ["$denied", "$total"]}}},
  {"$sort": {"denial_rate": -1}}
]
```

---

## Dual-Layer Architecture

HealthPay supports **two complementary MCP interfaces**:

1. **Official MongoDB MCP Server** (this directory) — generic, read-only Atlas access for judges
   and evaluators who want to explore the raw data
2. **Custom HealthPay MCP Server** (`src/mcp_server.py`) — 5 domain-specific tools with
   built-in FHIR logic, denial classification, and risk scoring

Both layers connect to the same MongoDB Atlas cluster. Use the official server for data
exploration; use the custom server for full RCM workflow automation.
