#!/usr/bin/env python3
"""
CLI script: Import Synthea FHIR Bundle JSON files into MongoDB Atlas.

Usage:
    python scripts/import_fhir_to_mongo.py [--dry-run] [--limit N] [--fhir-dir PATH]

Examples:
    # Dry run (parse only, no DB writes)
    python scripts/import_fhir_to_mongo.py --dry-run

    # Import first 50 resources per collection
    python scripts/import_fhir_to_mongo.py --limit 50

    # Custom FHIR directory
    python scripts/import_fhir_to_mongo.py --fhir-dir /path/to/fhir/output
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.mongodb_client import MongoDBClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_FHIR_DIR = str(
    Path(__file__).parent.parent / "synthea" / "output" / "fhir"
)

RESOURCE_COLLECTION_MAP = {
    "Claim": "claims",
    "ExplanationOfBenefit": "eobs",
    "Patient": "patients",
}


def parse_bundle(fpath: Path) -> dict[str, list]:
    """Extract Claim / EOB / Patient resources from a FHIR Bundle file."""
    result: dict[str, list] = {col: [] for col in RESOURCE_COLLECTION_MAP.values()}
    try:
        with open(fpath, encoding="utf-8") as f:
            bundle = json.load(f)
        for entry in bundle.get("entry", []):
            resource = entry.get("resource", {})
            rtype = resource.get("resourceType", "")
            col = RESOURCE_COLLECTION_MAP.get(rtype)
            if col:
                result[col].append(resource)
    except Exception as exc:
        logger.warning("Skipping %s — parse error: %s", fpath.name, exc)
    return result


def run(fhir_dir: str, dry_run: bool, limit: int) -> None:
    fhir_path = Path(fhir_dir)
    if not fhir_path.exists():
        logger.error("FHIR directory not found: %s", fhir_dir)
        sys.exit(1)

    json_files = sorted(fhir_path.glob("*.json"))
    logger.info("Found %d FHIR JSON files in %s", len(json_files), fhir_dir)

    client = MongoDBClient()
    status = client.test_connection()
    if status.get("mock"):
        logger.warning("Running in mock mode — no data will be written to MongoDB")
    elif not status.get("ok"):
        logger.error("MongoDB connection failed: %s", status.get("error"))
        sys.exit(1)

    totals: dict[str, int] = {col: 0 for col in RESOURCE_COLLECTION_MAP.values()}
    batch: dict[str, list] = {col: [] for col in RESOURCE_COLLECTION_MAP.values()}

    for fpath in json_files:
        extracted = parse_bundle(fpath)
        for col, docs in extracted.items():
            remaining = limit - totals[col]
            if remaining <= 0:
                continue
            chunk = docs[:remaining]
            batch[col].extend(chunk)
            totals[col] += len(chunk)

    # Report parsed counts
    for col, count in totals.items():
        logger.info("Parsed %d documents for collection '%s'", count, col)

    if dry_run:
        logger.info("[dry-run] No data written. Total parsed: %d", sum(totals.values()))
        return

    # Insert into MongoDB
    for col, docs in batch.items():
        if not docs:
            continue
        inserted = client.insert_many(col, docs)
        if inserted:
            logger.info("Inserted %d documents into '%s'", len(inserted), col)
        else:
            logger.info("Mock mode: would have inserted %d documents into '%s'", len(docs), col)

    logger.info("Import complete. Total: %d documents", sum(totals.values()))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Synthea FHIR data into MongoDB Atlas"
    )
    parser.add_argument(
        "--fhir-dir",
        default=DEFAULT_FHIR_DIR,
        help=f"Path to FHIR JSON directory (default: {DEFAULT_FHIR_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse files but do not write to MongoDB",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Max documents to import per collection (default: 100)",
    )
    args = parser.parse_args()
    run(fhir_dir=args.fhir_dir, dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()
