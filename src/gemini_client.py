"""
Gemini Client for HealthPay GCP.
Wraps Google Generative AI SDK with automatic mock fallback when GEMINI_API_KEY is not set.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_MOCK_CLAIM_ANALYSIS = (
    "[MOCK] Claim analysis: The claim appears to be a standard professional service claim. "
    "Key risk factors include missing prior authorization documentation and potential coding "
    "specificity issues. Recommend verifying ICD-10 codes are at highest specificity level "
    "and confirming payer authorization requirements before submission."
)

_MOCK_RECONCILIATION_SUMMARY = (
    "[MOCK] Reconciliation summary: Analysis complete. Identified discrepancies primarily "
    "in partial payment scenarios. Recommend reviewing denied claims for appeal opportunities "
    "and following up on unmatched EOBs with payer representatives."
)


class GeminiClient:
    """
    Gemini API client with mock fallback.
    If GEMINI_API_KEY is not set, all methods return deterministic mock responses.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        self._mock_mode = not bool(self.api_key)
        self._model = None

        if self._mock_mode:
            logger.warning("GEMINI_API_KEY not set — GeminiClient running in mock mode")
        else:
            self._init_sdk()

    def _init_sdk(self) -> None:
        """Initialize the google-generativeai SDK."""
        try:
            import google.generativeai as genai  # type: ignore
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(self.model_name)
            logger.info("Gemini SDK initialized: model=%s", self.model_name)
        except ImportError:
            logger.warning("google-generativeai not installed — falling back to mock mode")
            self._mock_mode = True
        except Exception as exc:
            logger.warning("Gemini SDK init failed: %s — falling back to mock mode", exc)
            self._mock_mode = True

    def generate_text(self, prompt: str) -> str:
        """
        Generate text from a prompt.

        Args:
            prompt: The input prompt string.

        Returns:
            Generated text, or a mock response if in mock mode.
        """
        if self._mock_mode:
            return f"[MOCK] Generated response for prompt: {prompt[:80]}..."

        try:
            response = self._model.generate_content(prompt)
            return response.text
        except Exception as exc:
            logger.error("Gemini generate_text failed: %s", exc)
            return f"[ERROR] Gemini API error: {exc}"

    def analyze_claim(self, claim_data: dict) -> str:
        """
        Analyze a single claim using Gemini.

        Args:
            claim_data: FHIR Claim document (dict).

        Returns:
            Analysis text from Gemini, or mock response.
        """
        if self._mock_mode:
            claim_id = claim_data.get("id", "unknown")
            return f"[MOCK] Claim {claim_id} analysis: Standard claim with no critical issues detected. Verify coding specificity and authorization status."

        claim_id = claim_data.get("id", "unknown")
        claim_type = ""
        for coding in claim_data.get("type", {}).get("coding", []):
            claim_type = coding.get("code", "")
            break

        total = claim_data.get("total", {})
        amount = total.get("value", 0) if isinstance(total, dict) else 0

        prompt = (
            f"You are a healthcare billing expert. Analyze this claim and identify risks:\n"
            f"Claim ID: {claim_id}\n"
            f"Type: {claim_type}\n"
            f"Amount: ${amount}\n"
            f"Diagnoses: {[d.get('diagnosisCodeableConcept', {}).get('coding', [{}])[0].get('code', '') for d in claim_data.get('diagnosis', [])]}\n"
            f"Provide a concise risk assessment and recommendations in 2-3 sentences."
        )

        try:
            response = self._model.generate_content(prompt)
            return response.text
        except Exception as exc:
            logger.error("Gemini analyze_claim failed: %s", exc)
            return _MOCK_CLAIM_ANALYSIS

    def summarize_reconciliation(self, results: dict) -> str:
        """
        Generate a natural-language summary of reconciliation results.

        Args:
            results: ReconciliationResult dict or summary dict.

        Returns:
            Summary text from Gemini, or mock response.
        """
        if self._mock_mode:
            summary = results.get("summary", results)
            matched = summary.get("matched_count", 0)
            discrepancies = summary.get("discrepancy_count", 0)
            total = summary.get("total_claims", 0)
            return (
                f"[MOCK] Reconciliation complete: {total} claims processed, "
                f"{matched} matched cleanly, {discrepancies} discrepancies found. "
                "Recommend prioritizing high-value discrepancies for immediate follow-up."
            )

        summary = results.get("summary", results)
        prompt = (
            f"You are a healthcare revenue cycle expert. Summarize these reconciliation results:\n"
            f"Total claims: {summary.get('total_claims', 0)}\n"
            f"Matched: {summary.get('matched_count', 0)}\n"
            f"Discrepancies: {summary.get('discrepancy_count', 0)}\n"
            f"Unmatched: {summary.get('unmatched_count', 0)}\n"
            f"Total claimed: ${summary.get('total_claimed_amount', 0)}\n"
            f"Total paid: ${summary.get('total_paid_amount', 0)}\n"
            f"Total discrepancy: ${summary.get('total_discrepancy_amount', 0)}\n"
            f"Provide actionable insights in 3-4 sentences."
        )

        try:
            response = self._model.generate_content(prompt)
            return response.text
        except Exception as exc:
            logger.error("Gemini summarize_reconciliation failed: %s", exc)
            return _MOCK_RECONCILIATION_SUMMARY

    @property
    def is_mock(self) -> bool:
        """True if running in mock mode (no real Gemini API key)."""
        return self._mock_mode
