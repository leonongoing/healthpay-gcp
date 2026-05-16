"""
MongoDB Atlas Client for HealthPay GCP.
Supports real Atlas connection and mock mode (when MONGODB_URI is not set).
"""

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MongoDBClient:
    """
    MongoDB Atlas client with automatic mock fallback.
    If MONGODB_URI is not set, all operations return empty data without error.
    """

    def __init__(self):
        self.uri = os.getenv("MONGODB_URI", "")
        self.db_name = os.getenv("MONGODB_DB", "healthpay")
        self._client = None
        self._db = None
        self._mock_mode = not bool(self.uri)

        if self._mock_mode:
            logger.warning("MONGODB_URI not set — running in mock mode (no data will be persisted)")
        else:
            self._connect()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        """Establish connection to MongoDB Atlas."""
        try:
            from pymongo import MongoClient
            from pymongo.server_api import ServerApi

            self._client = MongoClient(self.uri, server_api=ServerApi("1"), serverSelectionTimeoutMS=5000)
            self._db = self._client[self.db_name]
            logger.info("Connected to MongoDB Atlas: db=%s", self.db_name)
        except ImportError:
            logger.error("pymongo not installed — falling back to mock mode")
            self._mock_mode = True
        except Exception as exc:
            logger.error("MongoDB connection failed: %s — falling back to mock mode", exc)
            self._mock_mode = True

    def _collection(self, name: str):
        """Return a pymongo Collection, or None in mock mode."""
        if self._mock_mode or self._db is None:
            return None
        return self._db[name]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def test_connection(self) -> dict:
        """
        Ping the MongoDB deployment.
        Returns {"ok": True, "mock": False} on success,
                {"ok": True, "mock": True}  in mock mode,
                {"ok": False, "error": "..."}  on failure.
        """
        if self._mock_mode:
            return {"ok": True, "mock": True, "message": "Running in mock mode"}
        try:
            self._client.admin.command("ping")
            return {"ok": True, "mock": False, "message": "Connected to MongoDB Atlas"}
        except Exception as exc:
            return {"ok": False, "mock": False, "error": str(exc)}

    def get_claims(self, patient_id: Optional[str] = None, limit: int = 100) -> list:
        """
        Retrieve claims from the 'claims' collection.

        Args:
            patient_id: Filter by patient reference (optional).
            limit: Maximum number of documents to return.

        Returns:
            List of claim documents.
        """
        if self._mock_mode:
            return []
        col = self._collection("claims")
        query: dict = {}
        if patient_id:
            query["patient.reference"] = f"Patient/{patient_id}"
        return list(col.find(query, {"_id": 0}).limit(limit))

    def get_eobs(self, claim_id: Optional[str] = None, limit: int = 100) -> list:
        """
        Retrieve ExplanationOfBenefit documents from the 'eobs' collection.

        Args:
            claim_id: Filter by claim reference (optional).
            limit: Maximum number of documents to return.

        Returns:
            List of EOB documents.
        """
        if self._mock_mode:
            return []
        col = self._collection("eobs")
        query: dict = {}
        if claim_id:
            query["claim.reference"] = f"Claim/{claim_id}"
        return list(col.find(query, {"_id": 0}).limit(limit))

    def get_patients(self, limit: int = 100) -> list:
        """
        Retrieve patient documents from the 'patients' collection.

        Args:
            limit: Maximum number of documents to return.

        Returns:
            List of patient documents.
        """
        if self._mock_mode:
            return []
        col = self._collection("patients")
        return list(col.find({}, {"_id": 0}).limit(limit))

    def insert_document(self, collection: str, doc: dict) -> Optional[str]:
        """
        Insert a single document into the specified collection.

        Args:
            collection: Collection name.
            doc: Document to insert.

        Returns:
            Inserted document ID as string, or None in mock mode.
        """
        if self._mock_mode:
            logger.debug("Mock mode: skipping insert into %s", collection)
            return None
        col = self._collection(collection)
        result = col.insert_one(doc)
        return str(result.inserted_id)

    def insert_many(self, collection: str, docs: list) -> list:
        """
        Bulk-insert documents into the specified collection.

        Args:
            collection: Collection name.
            docs: List of documents to insert.

        Returns:
            List of inserted document IDs as strings, or empty list in mock mode.
        """
        if self._mock_mode or not docs:
            logger.debug("Mock mode or empty list: skipping bulk insert into %s", collection)
            return []
        col = self._collection(collection)
        result = col.insert_many(docs)
        return [str(oid) for oid in result.inserted_ids]

    def aggregate(self, collection: str, pipeline: list) -> list:
        """
        Run an aggregation pipeline on the specified collection.

        Args:
            collection: Collection name.
            pipeline: MongoDB aggregation pipeline stages.

        Returns:
            List of result documents, or empty list in mock mode.
        """
        if self._mock_mode:
            return []
        col = self._collection(collection)
        return list(col.aggregate(pipeline))

    def close(self) -> None:
        """Close the MongoDB connection."""
        if self._client:
            self._client.close()
            logger.info("MongoDB connection closed")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def is_mock(self) -> bool:
        """True if running in mock mode (no real MongoDB connection)."""
        return self._mock_mode
