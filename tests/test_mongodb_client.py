"""
Tests for MongoDBClient in mock mode.
No real MongoDB connection required.
"""

import os
import sys
import unittest
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

# Guarantee mock mode by unsetting MONGODB_URI before import
os.environ.pop("MONGODB_URI", None)

from src.mongodb_client import MongoDBClient


class TestMongoDBClientMockMode(unittest.TestCase):
    """All tests run against mock mode (MONGODB_URI not set)."""

    def setUp(self):
        os.environ.pop("MONGODB_URI", None)
        self.client = MongoDBClient()

    # ------------------------------------------------------------------
    # Test 1: mock mode is active
    # ------------------------------------------------------------------
    def test_mock_mode_active(self):
        """Client should enter mock mode when MONGODB_URI is not set."""
        self.assertTrue(self.client._mock_mode, "Expected mock mode to be active")

    # ------------------------------------------------------------------
    # Test 2: test_connection returns ok in mock mode
    # ------------------------------------------------------------------
    def test_connection_returns_ok_in_mock_mode(self):
        """test_connection() should return ok=True and mock=True."""
        result = self.client.test_connection()
        self.assertTrue(result.get("ok"), "Expected ok=True in mock mode")
        self.assertTrue(result.get("mock"), "Expected mock=True in mock mode")

    # ------------------------------------------------------------------
    # Test 3: get_claims returns empty list
    # ------------------------------------------------------------------
    def test_get_claims_returns_empty_list(self):
        """get_claims() should return [] in mock mode."""
        result = self.client.get_claims()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_get_claims_with_patient_id_returns_empty_list(self):
        """get_claims(patient_id=...) should also return [] in mock mode."""
        result = self.client.get_claims(patient_id="abc-123")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    # ------------------------------------------------------------------
    # Test 4: get_eobs returns empty list
    # ------------------------------------------------------------------
    def test_get_eobs_returns_empty_list(self):
        """get_eobs() should return [] in mock mode."""
        result = self.client.get_eobs()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_get_eobs_with_claim_id_returns_empty_list(self):
        """get_eobs(claim_id=...) should return [] in mock mode."""
        result = self.client.get_eobs(claim_id="claim-999")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    # ------------------------------------------------------------------
    # Test 5: get_patients returns empty list
    # ------------------------------------------------------------------
    def test_get_patients_returns_empty_list(self):
        """get_patients() should return [] in mock mode."""
        result = self.client.get_patients()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    # ------------------------------------------------------------------
    # Test 6: insert_document returns None (no-op)
    # ------------------------------------------------------------------
    def test_insert_document_returns_none_in_mock_mode(self):
        """insert_document() should return None without raising in mock mode."""
        result = self.client.insert_document("claims", {"resourceType": "Claim", "id": "test-1"})
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # Test 7: insert_many returns empty list (no-op)
    # ------------------------------------------------------------------
    def test_insert_many_returns_empty_list_in_mock_mode(self):
        """insert_many() should return [] without raising in mock mode."""
        docs = [{"resourceType": "Patient", "id": f"p-{i}"} for i in range(5)]
        result = self.client.insert_many("patients", docs)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_insert_many_empty_input_returns_empty_list(self):
        """insert_many() with empty list should return [] gracefully."""
        result = self.client.insert_many("claims", [])
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    # ------------------------------------------------------------------
    # Test 8: aggregate returns empty list (no-op)
    # ------------------------------------------------------------------
    def test_aggregate_returns_empty_list_in_mock_mode(self):
        """aggregate() should return [] without raising in mock mode."""
        pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
        result = self.client.aggregate("claims", pipeline)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    # ------------------------------------------------------------------
    # Test 9: no exception on repeated calls
    # ------------------------------------------------------------------
    def test_no_exception_on_repeated_calls(self):
        """Multiple calls in mock mode should never raise exceptions."""
        try:
            for _ in range(3):
                self.client.get_claims()
                self.client.get_eobs()
                self.client.get_patients()
                self.client.insert_document("claims", {"id": "x"})
                self.client.insert_many("eobs", [{"id": "y"}])
                self.client.aggregate("patients", [])
        except Exception as exc:
            self.fail(f"Unexpected exception in mock mode: {exc}")

    # ------------------------------------------------------------------
    # Test 10: limit parameter is accepted without error
    # ------------------------------------------------------------------
    def test_limit_parameter_accepted(self):
        """Methods accepting limit should not raise even with unusual values."""
        self.assertEqual(self.client.get_claims(limit=0), [])
        self.assertEqual(self.client.get_eobs(limit=1000), [])
        self.assertEqual(self.client.get_patients(limit=1), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
