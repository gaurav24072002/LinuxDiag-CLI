"""JSON rendering: exactly one valid JSON object, stable keys, null for unavailable.

Non-finite numbers (NaN/Infinity) are disallowed by the spec and sanitized to
null before serialization so the output is always strictly valid JSON.
"""
from __future__ import annotations

import json
import math

from linuxdiag.model import Report


def _sanitize(obj):
    """Recursively replace non-finite floats with None (JSON null)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


def render_json(report: Report) -> str:
    """Return the report as a single, strictly-valid JSON document."""
    payload = _sanitize(report.to_json())
    return json.dumps(payload, indent=2)
