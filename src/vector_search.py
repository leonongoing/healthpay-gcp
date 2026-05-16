"""
Vector Search for HealthPay GCP.
Generates embeddings for denial patterns and finds similar historical cases.
Uses Google text-embedding-004 when GEMINI_API_KEY is set, otherwise mock mode.
"""

import hashlib
import logging
import math
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Common CARC denial codes with descriptions (used for mock embeddings)
DENIAL_DESCRIPTIONS = {
    "CO-4": "The procedure code is inconsistent with the modifier used",
    "CO-11": "The diagnosis is inconsistent with the procedure",
    "CO-16": "Claim/service lacks information which is needed for adjudication",
    "CO-22": "This care may be covered by another payer per coordination of benefits",
    "CO-29": "The time limit for filing has expired",
    "CO-45": "Charges exceed your contracted/legislated fee arrangement",
    "CO-97": "The benefit for this service is included in the payment/allowance for another service",
    "CO-109": "Claim not covered by this payer/contractor",
    "CO-119": "Benefit maximum for this time period or occurrence has been reached",
    "CO-167": "This (these) diagnosis(es) is (are) not covered",
    "PR-1": "Deductible amount",
    "PR-2": "Coinsurance amount",
    "PR-3": "Co-payment amount",
    "OA-23": "The impact of prior payer(s) adjudication including payments and/or adjustments",
}


def _mock_embedding(text: str, dims: int = 768) -> list[float]:
    """Generate a deterministic pseudo-embedding from text (for testing without API key)."""
    h = hashlib.sha256(text.encode()).digest()
    # Expand hash bytes into `dims` floats in [-1, 1]
    floats = []
    for i in range(dims):
        byte_val = h[i % len(h)]
        floats.append((byte_val / 127.5) - 1.0)
    # L2-normalize
    norm = math.sqrt(sum(x * x for x in floats)) or 1.0
    return [x / norm for x in floats]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (norm_a * norm_b)


class VectorSearch:
    """
    Denial pattern vector search.
    - With GEMINI_API_KEY: uses Google text-embedding-004 for real semantic search
    - Without: uses deterministic mock embeddings (fully testable)
    - With MONGODB_URI: stores/retrieves from Atlas Vector Search
    - Without: uses in-memory index
    """

    def __init__(self, mongodb_client=None, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self._mock_mode = not bool(self.api_key)
        self._in_memory_index: list[dict] = []  # fallback when no MongoDB
        self.db = mongodb_client

        if self._mock_mode:
            logger.warning("GEMINI_API_KEY not set — VectorSearch running in mock mode")
            self._seed_mock_index()
        else:
            self._init_genai()

    def _init_genai(self):
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._genai = genai
            logger.info("Google GenAI initialized for embeddings")
        except Exception as exc:
            logger.warning("GenAI init failed: %s — falling back to mock", exc)
            self._mock_mode = True
            self._seed_mock_index()

    def _seed_mock_index(self):
        """Pre-populate in-memory index with common denial patterns."""
        for code, description in DENIAL_DESCRIPTIONS.items():
            self._in_memory_index.append({
                "denial_code": code,
                "description": description,
                "embedding": _mock_embedding(f"{code}: {description}"),
                "appeal_success_rate": 0.35 + (hash(code) % 40) / 100,
                "avg_resolution_days": 15 + (hash(code) % 30),
            })

    def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for text. Returns mock embedding if no API key."""
        if self._mock_mode:
            return _mock_embedding(text)
        try:
            result = self._genai.embed_content(
                model="models/text-embedding-004",
                content=text,
                task_type="SEMANTIC_SIMILARITY",
            )
            return result["embedding"]
        except Exception as exc:
            logger.warning("Embedding API failed: %s — using mock", exc)
            return _mock_embedding(text)

    def find_similar_denials(
        self,
        denial_description: str,
        limit: int = 5,
    ) -> list[dict]:
        """
        Find historically similar denial patterns.
        Returns list of similar cases with appeal success rates.
        """
        query_embedding = self.generate_embedding(denial_description)

        # Try MongoDB Atlas Vector Search first
        if self.db and not self.db._mock_mode:
            try:
                return self._atlas_vector_search(query_embedding, limit)
            except Exception as exc:
                logger.warning("Atlas Vector Search failed: %s — using in-memory", exc)

        # Fall back to in-memory cosine similarity
        return self._in_memory_search(query_embedding, limit)

    def _in_memory_search(self, query_embedding: list[float], limit: int) -> list[dict]:
        scored = []
        for item in self._in_memory_index:
            sim = _cosine_similarity(query_embedding, item["embedding"])
            scored.append({
                "denial_code": item["denial_code"],
                "description": item["description"],
                "similarity_score": round(sim, 4),
                "appeal_success_rate": item.get("appeal_success_rate", 0.3),
                "avg_resolution_days": item.get("avg_resolution_days", 20),
            })
        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scored[:limit]

    def _atlas_vector_search(self, query_embedding: list[float], limit: int) -> list[dict]:
        """Query MongoDB Atlas Vector Search index."""
        collection = self.db._db["denial_patterns"]
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "denial_pattern_vector_index",
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": limit * 10,
                    "limit": limit,
                }
            },
            {
                "$project": {
                    "denial_code": 1,
                    "description": 1,
                    "appeal_success_rate": 1,
                    "avg_resolution_days": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        return list(collection.aggregate(pipeline))

    def index_denial_patterns(self, eobs: list[dict]) -> int:
        """
        Index denial patterns from EOBs for future vector search.
        Returns number of patterns indexed.
        """
        indexed = 0
        seen_codes = set()

        for eob in eobs:
            for adj in eob.get("adjudication", []):
                for coding in adj.get("reason", {}).get("coding", []):
                    code = coding.get("code", "")
                    if not code or code in seen_codes:
                        continue
                    seen_codes.add(code)

                    description = DENIAL_DESCRIPTIONS.get(
                        code,
                        coding.get("display", f"Denial code {code}")
                    )
                    text = f"{code}: {description}"
                    embedding = self.generate_embedding(text)

                    pattern = {
                        "denial_code": code,
                        "description": description,
                        "embedding": embedding,
                        "appeal_success_rate": 0.35,
                        "avg_resolution_days": 20,
                    }

                    # Store in MongoDB if available
                    if self.db and not self.db._mock_mode:
                        try:
                            self.db._db["denial_patterns"].update_one(
                                {"denial_code": code},
                                {"$set": pattern},
                                upsert=True,
                            )
                        except Exception as exc:
                            logger.warning("Failed to index pattern %s: %s", code, exc)
                    else:
                        # Update in-memory index
                        existing = next(
                            (i for i, p in enumerate(self._in_memory_index)
                             if p["denial_code"] == code), None
                        )
                        if existing is not None:
                            self._in_memory_index[existing] = pattern
                        else:
                            self._in_memory_index.append(pattern)

                    indexed += 1

        logger.info("Indexed %d denial patterns", indexed)
        return indexed

    @property
    def is_mock(self) -> bool:
        return self._mock_mode
