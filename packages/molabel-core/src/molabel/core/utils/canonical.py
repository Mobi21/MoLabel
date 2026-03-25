"""Canonical label value conversion for consistent comparison.

This module provides a single, authoritative implementation of label value
canonicalization. All modules that need to compare label values should
import from here rather than maintaining their own copies.
"""

from __future__ import annotations

import json
from typing import Any


def canonical_label_value(value: Any) -> str:
    """Convert a label value to a canonical string for comparison.

    Handles None, bool, list, dict, and scalar types. Dicts are serialized
    with sorted keys for deterministic output. Lists are recursively
    canonicalized and sorted.

    Parameters
    ----------
    value:
        Any label value to canonicalize.

    Returns
    -------
    str
        A deterministic string representation suitable for equality checks.
    """
    if value is None:
        return "__null__"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ",".join(sorted(canonical_label_value(v) for v in value)) + "]"
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value)
