"""Deterministic, loss-aware control transformations for synthetic contexts."""
from __future__ import annotations

import copy
import hashlib
import re
from typing import Any


def _opaque(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"entity_{digest}"


def zero_evidence(context: dict[str, Any]) -> dict[str, Any]:
    """Keep the time anchor and schema, remove all evidence arrays."""
    result = copy.deepcopy(context)
    result["current"] = []
    result["history"] = []
    result["unknown"] = []
    return result


def opaque_entities(context: dict[str, Any]) -> dict[str, Any]:
    """Replace entity-like strings while preserving structure and timestamps."""
    result = copy.deepcopy(context)
    mapping: dict[str, str] = {}

    def transform(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: transform(item) for key, item in value.items()}
        if isinstance(value, list):
            return [transform(item) for item in value]
        if not isinstance(value, str):
            return value
        if value.endswith("_jst") or re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*", value):
            return value
        if value.startswith(("geo:", "person:", "venue:", "place:", "character:")):
            mapping.setdefault(value, _opaque(value))
            return mapping[value]
        return value

    transformed = transform(result)
    return {"context": transformed, "opaque_mapping_digest": hashlib.sha256(
        "\n".join(f"{key}={value}" for key, value in sorted(mapping.items())).encode("utf-8")
    ).hexdigest()}
