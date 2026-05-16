"""
Data Importer — bridges FHIR data sources into MongoDB collections.
Wraps import_fhir_to_mongo logic for programmatic use.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from .mongodb_client import MongoDBClient

logger = logging.getLogger(__name__)

FHIR_RESOURCE_MAP = {
    "Claim": "claims",
    "ExplanationOfBenefit": "eobs",
    "Patient": "patients",
}


def _extract_resources(bundle: dict) -> dict[str, list]:
    """Extract FHIR resources from a Bundle document."""
    result: dict[str, list] = {col: [] for col in FHIR_RESOURCE_MAP.values()}
    entries = bundle.get("entry", [])
    for entry in entries:
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType", "")
        col = FHIR_RESOURCE_MAP.get(rtype)
        if col:
            result[col].append(resource)
    return result


class FHIRImporter:
    """Import FHIR Bundle JSON files into MongoDB collections."""

    def __init__(self, client: Optional[MongoDBClient] = None):
        self.client = client or MongoDBClient()

    def import_directory(
        self,
        fhir_dir: str,
        dry_run: bool = False,
        limit: int = 100,
    ) -> dict:
        """
        Import all FHIR JSON files from a directory.

        Args:
            fhir_dir: Path to directory containing FHIR Bundle JSON files.
            dry_run: If True, parse only — do not write to MongoDB.
            limit: Maximum total resources to import per collection.

        Returns:
            Summary dict with counts per collection.
        """
        fhir_path = Path(fhir_dir)
        if not fhir_path.exists():
            raise FileNotFoundError(f"FHIR directory not found: {fhir_dir}")

        json_files = sorted(fhir_path.glob("*.json"))
        logger.info("Found %d FHIR JSON files in %s", len(json_files), fhir_dir)

        totals: dict[str, int] = {col: 0 for col in FHIR_RESOURCE_MAP.values()}
        batch: dict[str, list] = {col: [] for col in FHIR_RESOURCE_MAP.values()}

        for fpath in json_files:
            try:
                with open(fpath, encoding="utf-8") as f:
                    bundle = json.load(f)
                extracted = _extract_resources(bundle)
                for col, docs in extracted.items():
                    remaining = limit - totals[col]
                    if remaining <= 0:
                        continue
                    chunk = docs[:remaining]
                    batch[col].extend(chunk)
                    totals[col] += len(chunk)
            except Exception as exc:
                logger.warning("Failed to parse %s: %s", fpath.name, exc)

        if not dry_run:
            for col, docs in batch.items():
                if docs:
                    inserted = self.client.insert_many(col, docs)
                    logger.info("Inserted %d documents into '%s'", len(inserted), col)
        else:
            for col, docs in batch.items():
                logger.info("[dry-run] Would insert %d documents into '%s'", len(docs), col)

        return {
            "dry_run": dry_run,
            "counts": totals,
            "total": sum(totals.values()),
        }
