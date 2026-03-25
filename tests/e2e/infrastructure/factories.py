"""Data factories for all 6 E2E data types.

Each factory produces well-typed request payloads ready to POST to the API.
They load from the checked-in JSONL fixture files under tests/e2e/fixtures/
so tests always use the same canonical data set.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load all records from a JSONL file."""
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# Text classification — sentiment analysis on product reviews
# ---------------------------------------------------------------------------


def text_classification_records() -> list[dict[str, Any]]:
    """Return all 50 product review records for text classification."""
    return _load_jsonl(FIXTURES_DIR / "text_classification" / "reviews.jsonl")


def text_classification_schema_payload() -> dict[str, Any]:
    """Task schema payload for sentiment classification."""
    return {
        "task_slug": "sentiment",
        "task_type": "classification",
        "label_fields": [
            {
                "name": "sentiment",
                "field_type": "categorical",
                "options": ["positive", "negative", "neutral"],
                "required": True,
                "description": "Overall sentiment of the review",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Multi-label — topic tagging on news articles
# ---------------------------------------------------------------------------


def multi_label_records() -> list[dict[str, Any]]:
    """Return all 40 news article records for multi-label tagging."""
    return _load_jsonl(FIXTURES_DIR / "multi_label" / "articles.jsonl")


def multi_label_schema_payload() -> dict[str, Any]:
    """Task schema payload for multi-label topic classification."""
    return {
        "task_slug": "topic-tagging",
        "task_type": "multi_label",
        "label_fields": [
            {
                "name": "topics",
                "field_type": "multi_select",
                "options": [
                    "politics",
                    "sports",
                    "technology",
                    "science",
                    "health",
                    "entertainment",
                    "business",
                    "environment",
                ],
                "required": True,
                "description": "All applicable topic categories for this article",
            }
        ],
    }


# ---------------------------------------------------------------------------
# NER — named entity recognition on sentences
# ---------------------------------------------------------------------------


def ner_records() -> list[dict[str, Any]]:
    """Return all 30 sentences for NER annotation."""
    return _load_jsonl(FIXTURES_DIR / "ner" / "sentences.jsonl")


def ner_schema_payload() -> dict[str, Any]:
    """Task schema payload for NER (named entity recognition)."""
    return {
        "task_slug": "ner",
        "task_type": "span_annotation",
        "label_fields": [
            {
                "name": "entities",
                "field_type": "json",
                "required": True,
                "description": (
                    "JSON array of entity spans: "
                    '[{"start": 0, "end": 5, "label": "PERSON", "text": "Alice"}]'
                ),
            }
        ],
    }


# ---------------------------------------------------------------------------
# Content moderation — severity scoring on user comments
# ---------------------------------------------------------------------------


def content_moderation_records() -> list[dict[str, Any]]:
    """Return all 45 user comment records for content moderation."""
    return _load_jsonl(FIXTURES_DIR / "content_moderation" / "comments.jsonl")


def content_moderation_schema_payload() -> dict[str, Any]:
    """Task schema payload for content moderation (ordinal severity + rationale)."""
    return {
        "task_slug": "content-moderation",
        "task_type": "classification",
        "label_fields": [
            {
                "name": "severity",
                "field_type": "ordinal",
                "options": ["1", "2", "3", "4", "5"],
                "scale_min": 1,
                "scale_max": 5,
                "required": True,
                "description": (
                    "Severity of content violation: "
                    "1=safe, 2=borderline, 3=moderate, 4=severe, 5=extreme"
                ),
            },
            {
                "name": "rationale",
                "field_type": "text",
                "required": False,
                "description": "Brief explanation for the severity rating",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Pairwise comparison — preference ranking on LLM response pairs
# ---------------------------------------------------------------------------


def pairwise_comparison_records() -> list[dict[str, Any]]:
    """Return all 35 response pair records for pairwise comparison."""
    return _load_jsonl(FIXTURES_DIR / "pairwise_comparison" / "pairs.jsonl")


def pairwise_comparison_schema_payload() -> dict[str, Any]:
    """Task schema payload for pairwise preference comparison."""
    return {
        "task_slug": "pairwise-comparison",
        "task_type": "comparison",
        "label_fields": [
            {
                "name": "preferred",
                "field_type": "categorical",
                "options": ["A", "B", "tie"],
                "required": True,
                "description": "Which response is better, or tie if equal quality",
            },
            {
                "name": "confidence",
                "field_type": "numeric",
                "scale_min": 0.0,
                "scale_max": 1.0,
                "required": False,
                "description": "Confidence in the preference decision (0–1)",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Structured extraction — invoice / receipt field extraction
# ---------------------------------------------------------------------------


def structured_extraction_records() -> list[dict[str, Any]]:
    """Return all 25 invoice/receipt records for structured extraction."""
    return _load_jsonl(FIXTURES_DIR / "structured_extraction" / "invoices.jsonl")


def structured_extraction_schema_payload() -> dict[str, Any]:
    """Task schema payload for structured extraction from invoice text."""
    return {
        "task_slug": "invoice-extraction",
        "task_type": "extraction",
        "label_fields": [
            {
                "name": "vendor_name",
                "field_type": "text",
                "required": True,
                "description": "Name of the vendor or merchant",
            },
            {
                "name": "total_amount",
                "field_type": "numeric",
                "required": True,
                "description": "Total amount charged (numeric, no currency symbol)",
            },
            {
                "name": "date",
                "field_type": "text",
                "required": True,
                "description": "Invoice or transaction date in ISO format (YYYY-MM-DD)",
            },
            {
                "name": "currency",
                "field_type": "text",
                "required": False,
                "description": "Three-letter currency code, e.g. USD, EUR, GBP",
            },
            {
                "name": "line_items",
                "field_type": "json",
                "required": False,
                "description": (
                    "JSON array of line items: "
                    '[{"description": "Widget A", "quantity": 2, "price": 9.99}]'
                ),
            },
        ],
    }


# ---------------------------------------------------------------------------
# Generic import payload builder
# ---------------------------------------------------------------------------


def import_payload(
    source_type: str,
    records: list[dict[str, Any]],
    text_field: str = "text",
) -> dict[str, Any]:
    """Build a dataset import payload from a list of record dicts.

    Args:
        source_type: e.g. ``"jsonl"``, ``"csv"``.
        records: List of record dicts (as loaded from fixture JSONL files).
        text_field: The field name that contains the main text for labeling.

    Returns:
        A dict suitable for POST /datasets/{ds_id}/import.
    """
    return {
        "source_type": source_type,
        "records": records,
        "text_field": text_field,
    }
