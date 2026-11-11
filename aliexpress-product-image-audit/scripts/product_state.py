# -*- coding: utf-8 -*-
"""Pure helpers for token-opt-v1 product preconditions and verification."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

MUTABLE_STATE_FIELDS = (
    "titleEn", "title", "titleTranslationZh", "descriptionJson", "images", "skus",
    "price", "weight", "identityJson", "brand", "brandId", "status",
)


def project_mutable_state(product: dict[str, Any]) -> dict[str, Any]:
    """Return the complete write-sensitive state; list order is intentionally preserved."""
    return {key: deepcopy(product.get(key)) for key in MUTABLE_STATE_FIELDS}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_state_hash(product: dict[str, Any]) -> str:
    payload = canonical_json(project_mutable_state(product)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def diff_state(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    left, right = project_mutable_state(before), project_mutable_state(after)
    return {key: {"before": left[key], "after": right[key]}
            for key in MUTABLE_STATE_FIELDS if left[key] != right[key]}


def identity_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("identityJson must be a JSON object or object string")
