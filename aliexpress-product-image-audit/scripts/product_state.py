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
    state={key: deepcopy(product.get(key)) for key in MUTABLE_STATE_FIELDS}
    # The API accepts serialized identity JSON and may return either representation.
    if isinstance(state.get('identityJson'),str):
        try:
            parsed=json.loads(state['identityJson'])
            if isinstance(parsed,dict):state['identityJson']=parsed
        except ValueError:pass
    return state


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_state_hash(product: dict[str, Any]) -> str:
    payload = canonical_json(project_mutable_state(product)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


SERVER_DERIVED_SKU_FIELDS = frozenset({'discountPrice', 'shippingFee'})


def description_content_preserved(expected, observed, *, source_title=None, saved_title=None):
    """Allow only the site's confirmed generated top-title synchronization.

    This is a save-contract comparison, never an audit/URL extraction operation.
    Collected content and every other attribute must remain unchanged.
    """
    if type(expected) is not type(observed):
        return False
    if expected == observed:
        return True
    if not isinstance(source_title, str) or not source_title or not isinstance(saved_title, str) or not saved_title:
        return False
    try:
        left = json.loads(expected) if isinstance(expected, str) else deepcopy(expected)
        right = json.loads(observed) if isinstance(observed, str) else deepcopy(observed)
        if not isinstance(left, list) or not isinstance(right, list) or not left or not right:
            return False
        old, new = left[0], right[0]
        if old.get('type') != 'text' or new.get('type') != 'text':
            return False
        a, b = old['texts'][0], new['texts'][0]
        if a.get('class') != 'title' or b.get('class') != 'title':
            return False
        if a.get('content') != source_title or b.get('content') != saved_title:
            return False
        a['content'] = saved_title
        return canonical_json(left) == canonical_json(right)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        return False


def saved_state_matches(expected: dict[str, Any], observed: dict[str, Any], *, source=None) -> bool:
    """Post-save comparison only; source hashes and outbound values stay exact.

    The site recomputes the two derived USD amounts. They are outside audit
    scope per user instruction; never normalize the stored snapshots themselves.
    """
    if (('descriptionJson' in expected) != ('descriptionJson' in observed)
            or type(expected.get('descriptionJson')) is not type(observed.get('descriptionJson'))):
        return False
    def projection(product):
        state = project_mutable_state(product)
        if isinstance(state.get('skus'), list):
            for sku in state['skus']:
                if isinstance(sku, dict):
                    for field in SERVER_DERIVED_SKU_FIELDS:
                        sku.pop(field, None)
        return state
    left, right = projection(expected), projection(observed)
    if source is not None and description_content_preserved(
            expected.get('descriptionJson'), observed.get('descriptionJson'),
            source_title=source.get('titleEn'), saved_title=expected.get('titleEn')):
        # Preserve field presence and type; normalize only a validated header change.
        if ('descriptionJson' in expected) == ('descriptionJson' in observed):
            right['descriptionJson'] = deepcopy(left['descriptionJson'])
    return canonical_json(left) == canonical_json(right)


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
