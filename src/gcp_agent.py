"""
Google Cloud Agent integration for HealthPay GCP.
Uses google-generativeai (Gemini) with function calling to orchestrate the 5 MCP tools.
Falls back to mock mode when GEMINI_API_KEY is not set.
"""

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Tool definitions for Gemini function calling
TOOL_DECLARATIONS = [
    {
        "name": "reconcile_claims",
        "description": "Reconcile healthcare claims against EOBs and identify payment discrepancies. Returns matched pairs, discrepancies, and an AI-generated summary.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "Filter by patient ID (optional, omit for all patients)"},
                "limit": {"type": "integer", "description": "Maximum number of claims to process (default: 100)"},
            },
        },
    },
    {
        "name": "analyze_denials",
        "description": "Analyze claim denials, classify root causes using CARC codes, and generate appeal strategies.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "Filter by patient ID (optional)"},
                "limit": {"type": "integer", "description": "Maximum number of EOBs to analyze (default: 50)"},
            },
        },
    },
    {
        "name": "get_financial_vitals",
        "description": "Return A/R aging dashboard, collection rates, and payer performance metrics.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "predict_payment_risk",
        "description": "Score a specific claim by payment probability before submission.",
        "parameters": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string", "description": "The claim ID to score (required)"},
            },
            "required": ["claim_id"],
        },
    },
    {
        "name": "suggest_coding_optimization",
        "description": "Identify ICD-10/CPT coding issues that cause denials and suggest corrections.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string", "description": "Filter by patient ID (optional)"},
                "limit": {"type": "integer", "description": "Maximum number of claims to analyze (default: 50)"},
            },
        },
    },
]

SYSTEM_INSTRUCTION = """You are HealthPay Intelligence Agent, an expert in healthcare revenue cycle management.

You help healthcare administrators:
- Reconcile claims against Explanation of Benefits (EOBs)
- Analyze and appeal denied claims
- Monitor financial health metrics (A/R aging, collection rates)
- Predict payment risk before claim submission
- Optimize ICD-10/CPT coding to reduce denials

Always use the available tools to provide data-driven answers. When presenting results:
- Lead with the most actionable insight
- Quantify the financial impact when possible
- Prioritize high-value discrepancies and denials
- Suggest specific next steps

Be concise and professional. Healthcare administrators are busy — get to the point."""


class HealthPayAgent:
    """
    HealthPay Intelligence Agent powered by Gemini.
    Uses function calling to orchestrate the 5 MCP tools.
    Falls back to mock mode when GEMINI_API_KEY is not set.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self._mock_mode = not bool(self.api_key)
        self._model = None
        self.conversation_history = []

        if self._mock_mode:
            logger.warning("GEMINI_API_KEY not set — HealthPayAgent running in mock mode")
        else:
            self._init_model()

    def _init_model(self):
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)

            tools = [{"function_declarations": TOOL_DECLARATIONS}]
            self._model = genai.GenerativeModel(
                model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-pro"),
                system_instruction=SYSTEM_INSTRUCTION,
                tools=tools,
            )
            self._chat = self._model.start_chat(history=[])
            logger.info("HealthPayAgent initialized with Gemini 1.5 Pro")
        except Exception as exc:
            logger.warning("Gemini init failed: %s — falling back to mock", exc)
            self._mock_mode = True

    def _execute_tool(self, tool_name: str, tool_args: dict) -> Any:
        """Execute a tool call from Gemini function calling."""
        from src.mcp_server import call_tool
        try:
            return call_tool(tool_name, tool_args)
        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc)
            return {"error": str(exc)}

    def chat(self, user_message: str) -> str:
        """
        Send a message to the agent and get a response.
        Handles multi-turn function calling automatically.
        """
        if self._mock_mode:
            return self._mock_response(user_message)

        try:
            response = self._chat.send_message(user_message)

            # Handle function calling loop
            max_rounds = 5
            for _ in range(max_rounds):
                if not response.candidates:
                    break

                candidate = response.candidates[0]
                if not candidate.content.parts:
                    break

                # Check for function calls
                function_calls = [
                    p for p in candidate.content.parts
                    if hasattr(p, "function_call") and p.function_call.name
                ]

                if not function_calls:
                    # No more function calls — return text response
                    text_parts = [
                        p.text for p in candidate.content.parts
                        if hasattr(p, "text") and p.text
                    ]
                    return "\n".join(text_parts) if text_parts else "[No response]"

                # Execute all function calls and send results back
                function_responses = []
                for part in function_calls:
                    fc = part.function_call
                    result = self._execute_tool(fc.name, dict(fc.args))
                    function_responses.append({
                        "function_response": {
                            "name": fc.name,
                            "response": {"result": json.dumps(result, default=str)},
                        }
                    })

                response = self._chat.send_message(function_responses)

            return "[Max function call rounds reached]"

        except Exception as exc:
            logger.error("Agent chat failed: %s", exc)
            return f"[ERROR] {exc}"

    def _mock_response(self, user_message: str) -> str:
        """Return a mock response for testing without API key."""
        msg_lower = user_message.lower()
        if "reconcil" in msg_lower:
            return "[MOCK] Reconciliation analysis: 0 claims processed (mock mode — no MongoDB data). In production, I would analyze claims against EOBs and identify payment discrepancies."
        elif "denial" in msg_lower:
            return "[MOCK] Denial analysis: 0 EOBs analyzed (mock mode). In production, I would classify denial root causes using CARC codes and generate appeal strategies."
        elif "financial" in msg_lower or "vital" in msg_lower or "aging" in msg_lower:
            return "[MOCK] Financial vitals: A/R aging report generated (mock mode — all zeros). In production, I would show aging buckets, collection rates, and payer performance."
        elif "risk" in msg_lower:
            return "[MOCK] Payment risk prediction requires a specific claim ID. In production, I would score the claim by payment probability."
        elif "coding" in msg_lower or "icd" in msg_lower or "cpt" in msg_lower:
            return "[MOCK] Coding optimization: 0 claims analyzed (mock mode). In production, I would identify ICD-10/CPT issues causing denials."
        else:
            return f"[MOCK] HealthPay Agent received: '{user_message}'. I can help with: claim reconciliation, denial analysis, financial vitals, payment risk prediction, and coding optimization."

    @property
    def is_mock(self) -> bool:
        return self._mock_mode

    def get_status(self) -> dict:
        """Return agent status information."""
        from src.mcp_server import TOOLS
        return {
            "mode": "mock" if self._mock_mode else "live",
            "model": os.getenv("GEMINI_MODEL", "gemini-2.5-pro") if not self._mock_mode else "mock",
            "tools_available": len(TOOLS),
            "tool_names": list(TOOLS.keys()),
            "api_key_set": bool(self.api_key),
        }
