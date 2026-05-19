"""
mongodb_mcp_bridge.py — Official MongoDB MCP Server Compatibility Bridge

Demonstrates how HealthPay queries map to official mongodb-mcp-server tool calls.
Runs in mock mode by default (no real DB connection required).

Usage:
    python src/mongodb_mcp_bridge.py              # mock mode
    python src/mongodb_mcp_bridge.py --live       # real Atlas (requires MONGODB_URI)

Official MCP Server:
    npx -y mongodb-mcp-server --readOnly
    env: MDB_MCP_CONNECTION_STRING=mongodb+srv://...
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_CLAIMS = [
    {
        "_id": "claim_001",
        "resourceType": "ClaimResponse",
        "outcome": "denied",
        "insurer": "BlueCross BlueShield",
        "patient_ref": "Patient/pat_001",
        "submitted_amount": 1250.00,
        "carc_code": "4",
        "carc_description": "Service/procedure inconsistent with patient age",
        "created": (datetime.now() - timedelta(days=15)).isoformat(),
    },
    {
        "_id": "claim_002",
        "resourceType": "ClaimResponse",
        "outcome": "complete",
        "insurer": "Aetna",
        "patient_ref": "Patient/pat_002",
        "submitted_amount": 850.00,
        "created": (datetime.now() - timedelta(days=8)).isoformat(),
    },
    {
        "_id": "claim_003",
        "resourceType": "ClaimResponse",
        "outcome": "denied",
        "insurer": "United Healthcare",
        "patient_ref": "Patient/pat_003",
        "submitted_amount": 3200.00,
        "carc_code": "197",
        "carc_description": "Precertification/authorization/notification absent",
        "created": (datetime.now() - timedelta(days=3)).isoformat(),
    },
    {
        "_id": "claim_004",
        "resourceType": "ClaimResponse",
        "outcome": "denied",
        "insurer": "BlueCross BlueShield",
        "patient_ref": "Patient/pat_004",
        "submitted_amount": 675.00,
        "carc_code": "96",
        "carc_description": "Non-covered charge(s)",
        "created": (datetime.now() - timedelta(days=1)).isoformat(),
    },
    {
        "_id": "claim_005",
        "resourceType": "ClaimResponse",
        "outcome": "complete",
        "insurer": "Cigna",
        "patient_ref": "Patient/pat_005",
        "submitted_amount": 420.00,
        "created": datetime.now().isoformat(),
    },
]

MOCK_EOBS = [
    {
        "_id": "eob_001",
        "resourceType": "ExplanationOfBenefit",
        "claim_ref": "claim_001",
        "outcome": "denied",
        "payment_amount": 0.00,
    },
    {
        "_id": "eob_002",
        "resourceType": "ExplanationOfBenefit",
        "claim_ref": "claim_002",
        "outcome": "complete",
        "payment_amount": 765.00,
    },
]


# ---------------------------------------------------------------------------
# Mock MCP executor
# ---------------------------------------------------------------------------

class MockMCPExecutor:
    """Simulates official mongodb-mcp-server tool responses in mock mode."""

    def __init__(self, database: str = "healthpay"):
        self.database = database
        self._collections = {
            "claims": MOCK_CLAIMS,
            "eobs": MOCK_EOBS,
            "patients": [],
        }

    def _matches(self, doc: dict, filter_: dict) -> bool:
        for key, value in filter_.items():
            if isinstance(value, dict):
                op, operand = next(iter(value.items()))
                doc_val = doc.get(key)
                if op == "$eq" and doc_val != operand:
                    return False
                if op == "$ne" and doc_val == operand:
                    return False
                if op == "$in" and doc_val not in operand:
                    return False
            else:
                if doc.get(key) != value:
                    return False
        return True

    def find(self, collection: str, filter: dict = None, limit: int = 20, skip: int = 0) -> list:
        """Mirrors the official MCP `find` tool."""
        docs = list(self._collections.get(collection, []))
        if filter:
            docs = [d for d in docs if self._matches(d, filter)]
        return docs[skip: skip + limit]

    def aggregate(self, collection: str, pipeline: list) -> list:
        """Mirrors the official MCP `aggregate` tool (simplified mock)."""
        docs = list(self._collections.get(collection, []))

        for stage in pipeline:
            if "$match" in stage:
                docs = [d for d in docs if self._matches(d, stage["$match"])]
            elif "$group" in stage:
                spec = stage["$group"]
                id_expr = spec.get("_id")
                groups = {}
                for doc in docs:
                    if isinstance(id_expr, str) and id_expr.startswith("$"):
                        key = doc.get(id_expr[1:])
                    else:
                        key = id_expr
                    if key not in groups:
                        groups[key] = {"_id": key}
                    for out_field, agg_expr in spec.items():
                        if out_field == "_id":
                            continue
                        if isinstance(agg_expr, dict):
                            op2 = list(agg_expr.keys())[0]
                            val_expr = agg_expr[op2]
                            if op2 == "$sum":
                                if val_expr == 1:
                                    groups[key][out_field] = groups[key].get(out_field, 0) + 1
                                elif isinstance(val_expr, str) and val_expr.startswith("$"):
                                    groups[key][out_field] = groups[key].get(out_field, 0) + doc.get(val_expr[1:], 0)
                docs = list(groups.values())
            elif "$sort" in stage:
                for field, direction in reversed(list(stage["$sort"].items())):
                    docs = sorted(docs, key=lambda d: d.get(field, 0), reverse=(direction == -1))
            elif "$limit" in stage:
                docs = docs[: stage["$limit"]]

        return docs

    def list_collections(self) -> list:
        """Mirrors the official MCP `listCollections` tool."""
        return list(self._collections.keys())

    def count(self, collection: str, filter: dict = None) -> int:
        """Mirrors the official MCP `count` tool."""
        return len(self.find(collection, filter=filter, limit=10000))


# ---------------------------------------------------------------------------
# Live MCP executor (calls real mongodb-mcp-server via subprocess)
# ---------------------------------------------------------------------------

class LiveMCPExecutor:
    """
    Calls the official mongodb-mcp-server via subprocess JSON-RPC.
    Requires: MDB_MCP_CONNECTION_STRING env var set.
    """

    def __init__(self, database: str = "healthpay"):
        self.database = database
        conn = os.environ.get("MDB_MCP_CONNECTION_STRING") or os.environ.get("MONGODB_URI")
        if not conn:
            raise ValueError(
                "Set MDB_MCP_CONNECTION_STRING or MONGODB_URI to use live mode.\n"
                "Example: export MDB_MCP_CONNECTION_STRING=mongodb+srv://USER:PASS@cluster.mongodb.net/healthpay"
            )
        self._conn = conn

    def _call_tool(self, tool_name: str, params: dict) -> Any:
        import subprocess, uuid
        request = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": params},
        }
        proc = subprocess.run(
            ["npx", "-y", "mongodb-mcp-server", "--readOnly"],
            input=json.dumps(request) + "\n",
            capture_output=True,
            text=True,
            env={**os.environ, "MDB_MCP_CONNECTION_STRING": self._conn},
            timeout=30,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"MCP server error: {proc.stderr}")
        response = json.loads(proc.stdout.strip().split("\n")[-1])
        if "error" in response:
            raise RuntimeError(f"MCP tool error: {response['error']}")
        return response.get("result", {}).get("content", [{}])[0].get("text", "[]")

    def find(self, collection: str, filter: dict = None, limit: int = 20, skip: int = 0) -> list:
        result = self._call_tool("find", {
            "collection": collection,
            "database": self.database,
            "filter": filter or {},
            "limit": limit,
            "skip": skip,
        })
        return json.loads(result) if isinstance(result, str) else result

    def aggregate(self, collection: str, pipeline: list) -> list:
        result = self._call_tool("aggregate", {
            "collection": collection,
            "database": self.database,
            "pipeline": pipeline,
        })
        return json.loads(result) if isinstance(result, str) else result

    def list_collections(self) -> list:
        result = self._call_tool("listCollections", {"database": self.database})
        return json.loads(result) if isinstance(result, str) else result

    def count(self, collection: str, filter: dict = None) -> int:
        result = self._call_tool("count", {
            "collection": collection,
            "database": self.database,
            "query": filter or {},
        })
        return int(result) if isinstance(result, (str, int)) else 0


# ---------------------------------------------------------------------------
# HealthPay query examples using official MCP tools
# ---------------------------------------------------------------------------

def example_find_denied_claims(mcp) -> None:
    """Example 1: Use `find` tool to query denied claims."""
    print("\n=== Example 1: Find Denied Claims (MCP `find` tool) ===")
    print("Tool call: find(collection=\"claims\", filter={\"outcome\": \"denied\"}, limit=10)")

    results = mcp.find(
        collection="claims",
        filter={"outcome": "denied"},
        limit=10,
    )

    print(f"Found {len(results)} denied claims:")
    for claim in results:
        amount = claim.get("submitted_amount", 0)
        insurer = claim.get("insurer", "Unknown")
        carc = claim.get("carc_code", "N/A")
        desc = claim.get("carc_description", "")
        print(f"  [{claim['_id']}] ${amount:,.2f} | {insurer} | CARC {carc}: {desc}")


def example_denial_analysis_by_payer(mcp) -> None:
    """Example 2: Use `aggregate` tool for denial analysis by payer."""
    print("\n=== Example 2: Denial Analysis by Payer (MCP `aggregate` tool) ===")
    pipeline = [
        {"$match": {"outcome": "denied"}},
        {"$group": {
            "_id": "$insurer",
            "denial_count": {"$sum": 1},
            "total_denied_amount": {"$sum": "$submitted_amount"},
        }},
        {"$sort": {"denial_count": -1}},
    ]
    print(f"Pipeline: {json.dumps(pipeline, indent=2)}")

    results = mcp.aggregate(collection="claims", pipeline=pipeline)

    print(f"Denial breakdown by payer ({len(results)} payers):")
    for row in results:
        payer = row.get("_id", "Unknown")
        count = row.get("denial_count", 0)
        amount = row.get("total_denied_amount", 0)
        print(f"  {payer}: {count} denials | ${amount:,.2f} at risk")


def example_carc_code_distribution(mcp) -> None:
    """Example 3: Use `aggregate` to analyze CARC code distribution."""
    print("\n=== Example 3: CARC Code Distribution (MCP `aggregate` tool) ===")
    pipeline = [
        {"$match": {"outcome": "denied"}},
        {"$group": {
            "_id": "$carc_code",
            "count": {"$sum": 1},
            "total_amount": {"$sum": "$submitted_amount"},
        }},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]

    results = mcp.aggregate(collection="claims", pipeline=pipeline)

    print(f"Top denial reason codes:")
    for row in results:
        code = row.get("_id", "N/A")
        count = row.get("count", 0)
        amount = row.get("total_amount", 0)
        print(f"  CARC {code}: {count} claims | ${amount:,.2f}")


def example_list_collections(mcp) -> None:
    """Example 4: Use `listCollections` to explore the database."""
    print("\n=== Example 4: List Collections (MCP `listCollections` tool) ===")
    collections = mcp.list_collections()
    print(f"Collections in '{mcp.database}' database: {collections}")

    for coll in collections:
        total = mcp.count(coll)
        denied = mcp.count(coll, filter={"outcome": "denied"}) if coll == "claims" else 0
        if coll == "claims":
            print(f"  {coll}: {total} documents ({denied} denied)")
        else:
            print(f"  {coll}: {total} documents")


def example_eob_reconciliation(mcp) -> None:
    """Example 5: Cross-reference claims with EOBs using `find`."""
    print("\n=== Example 5: EOB Reconciliation (MCP `find` tool) ===")

    denied_claims = mcp.find("claims", filter={"outcome": "denied"}, limit=5)
    denied_ids = [c["_id"] for c in denied_claims]

    eobs = mcp.find("eobs", filter={"outcome": "denied"}, limit=10)

    print(f"Denied claims: {denied_ids}")
    print(f"Matching EOBs: {[e['_id'] for e in eobs]}")
    print(f"EOBs with $0 payment: {sum(1 for e in eobs if e.get('payment_amount', 0) == 0)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    live_mode = "--live" in sys.argv

    if live_mode:
        print("Running in LIVE mode (official mongodb-mcp-server)")
        try:
            mcp = LiveMCPExecutor(database="healthpay")
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)
    else:
        print("Running in MOCK mode (no real DB connection needed)")
        print("Use --live flag with MDB_MCP_CONNECTION_STRING set for real Atlas data.")
        mcp = MockMCPExecutor(database="healthpay")

    print(f"\nDatabase: {mcp.database}")
    print("Official MongoDB MCP Server tools: find, aggregate, listCollections, count")
    print("-" * 60)

    example_list_collections(mcp)
    example_find_denied_claims(mcp)
    example_denial_analysis_by_payer(mcp)
    example_carc_code_distribution(mcp)
    example_eob_reconciliation(mcp)

    print("\n" + "=" * 60)
    print("All examples completed successfully.")
    print("\nTo use with real Atlas data:")
    print("  export MDB_MCP_CONNECTION_STRING=mongodb+srv://USER:PASS@cluster.mongodb.net/healthpay")
    print("  python src/mongodb_mcp_bridge.py --live")
    print("\nTo use with Claude Desktop or Gemini CLI:")
    print("  See mcp-config/ directory for configuration examples.")


if __name__ == "__main__":
    main()
