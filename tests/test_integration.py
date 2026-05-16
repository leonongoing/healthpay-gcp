"""
Integration tests for HealthPay GCP — mock mode (no real MongoDB or Gemini API key needed).
"""

import sys
import os
import pytest

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# MongoDB client tests (already covered in test_mongodb_client.py)
# ---------------------------------------------------------------------------

class TestGeminiClientMockMode:
    def test_mock_mode_active_without_api_key(self):
        from src.gemini_client import GeminiClient
        client = GeminiClient(api_key="")
        assert client.is_mock is True

    def test_generate_text_returns_string(self):
        from src.gemini_client import GeminiClient
        client = GeminiClient(api_key="")
        result = client.generate_text("Summarize this claim.")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_analyze_claim_returns_string(self):
        from src.gemini_client import GeminiClient
        client = GeminiClient(api_key="")
        claim = {"id": "claim-001", "type": {"coding": [{"code": "professional"}]}, "total": {"value": 500.0}}
        result = client.analyze_claim(claim)
        assert isinstance(result, str)
        assert "claim-001" in result or "MOCK" in result

    def test_summarize_reconciliation_returns_string(self):
        from src.gemini_client import GeminiClient
        client = GeminiClient(api_key="")
        results = {"summary": {"total_claims": 10, "matched_count": 8, "discrepancy_count": 2}}
        result = client.summarize_reconciliation(results)
        assert isinstance(result, str)
        assert len(result) > 0


class TestFinancialVitalsMockMode:
    def test_get_ar_aging_returns_report(self):
        from src.financial_vitals import FinancialVitals
        vitals = FinancialVitals()
        report = vitals.get_ar_aging()
        assert hasattr(report, "buckets")
        assert hasattr(report, "total_ar")

    def test_get_collection_rate_returns_report(self):
        from src.financial_vitals import FinancialVitals
        vitals = FinancialVitals()
        report = vitals.get_collection_rate()
        assert hasattr(report, "collection_rate")

    def test_get_payer_performance_returns_list(self):
        from src.financial_vitals import FinancialVitals
        vitals = FinancialVitals()
        result = vitals.get_payer_performance()
        assert isinstance(result, list)

    def test_get_full_report_returns_report(self):
        from src.financial_vitals import FinancialVitals
        vitals = FinancialVitals()
        report = vitals.get_full_report()
        assert hasattr(report, "generated_at")
        assert hasattr(report, "ar_aging")
        assert hasattr(report, "collection_rate")


class TestMCPServerMockMode:
    def test_list_tools_returns_5_tools(self):
        from src.mcp_server import list_tools
        tools = list_tools()
        assert len(tools) == 5
        names = {t["name"] for t in tools}
        assert "reconcile_claims" in names
        assert "analyze_denials" in names
        assert "get_financial_vitals" in names
        assert "predict_payment_risk" in names
        assert "suggest_coding_optimization" in names

    def test_each_tool_has_required_fields(self):
        from src.mcp_server import list_tools
        for tool in list_tools():
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool

    def test_call_get_financial_vitals(self):
        from src.mcp_server import call_tool
        result = call_tool("get_financial_vitals", {})
        assert isinstance(result, dict)

    def test_call_unknown_tool_raises(self):
        from src.mcp_server import call_tool
        with pytest.raises(ValueError, match="Unknown tool"):
            call_tool("nonexistent_tool", {})

    def test_call_reconcile_claims_mock(self):
        from src.mcp_server import call_tool
        result = call_tool("reconcile_claims", {"limit": 5})
        assert isinstance(result, dict)

    def test_call_analyze_denials_mock(self):
        from src.mcp_server import call_tool
        result = call_tool("analyze_denials", {"limit": 5})
        assert isinstance(result, dict)

    def test_call_suggest_coding_optimization_mock(self):
        from src.mcp_server import call_tool
        result = call_tool("suggest_coding_optimization", {"limit": 5})
        assert isinstance(result, dict)


class TestVectorSearchMockMode:
    def test_mock_mode_active_without_api_key(self):
        from src.vector_search import VectorSearch
        vs = VectorSearch(api_key="")
        assert vs._mock_mode is True

    def test_generate_embedding_returns_list(self):
        from src.vector_search import VectorSearch
        vs = VectorSearch(api_key="")
        emb = vs.generate_embedding("claim denial CO-4 procedure code inconsistent")
        assert isinstance(emb, list)
        assert len(emb) == 768

    def test_find_similar_denials_returns_results(self):
        from src.vector_search import VectorSearch
        vs = VectorSearch(api_key="")
        results = vs.find_similar_denials("procedure code inconsistent with modifier", limit=3)
        assert isinstance(results, list)
        assert len(results) <= 3
        for r in results:
            assert "denial_code" in r
            assert "similarity_score" in r

    def test_index_denial_patterns_returns_count(self):
        from src.vector_search import VectorSearch
        vs = VectorSearch(api_key="")
        eobs = [
            {"id": "eob-1", "adjudication": [{"category": {"coding": [{"code": "benefit"}]}, "reason": {"coding": [{"code": "CO-4"}]}}]},
        ]
        count = vs.index_denial_patterns(eobs)
        assert isinstance(count, int)


class TestHealthPayAgentMockMode:
    def test_mock_mode_active_without_api_key(self):
        from src.gcp_agent import HealthPayAgent
        agent = HealthPayAgent(api_key="")
        assert agent._mock_mode is True

    def test_chat_returns_string(self):
        from src.gcp_agent import HealthPayAgent
        agent = HealthPayAgent(api_key="")
        response = agent.chat("What are the top denial reasons?")
        assert isinstance(response, str)
        assert len(response) > 0

    def test_get_status_returns_dict(self):
        from src.gcp_agent import HealthPayAgent
        agent = HealthPayAgent(api_key="")
        status = agent.get_status()
        assert "mode" in status
        assert "model" in status
        assert "tools_available" in status
        assert status["tools_available"] == 5
