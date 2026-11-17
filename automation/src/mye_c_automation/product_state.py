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
    """Opaque protected field: exact type/value only, never parse Description."""
    return type(expected) is type(observed) and expected == observed


def generated_title_readback_preserved(expected, observed, *, source_title=None, saved_title=None):
    """Recognize only the site's marked title mirror after an authorized title save.

    Outbound Description and input hashes remain exact. This never edits a snapshot.
    """
    if description_content_preserved(expected, observed):
        return True
    if (not isinstance(source_title, str) or not source_title or
            not isinstance(saved_title, str) or not saved_title or source_title == saved_title or
            type(expected) is not str or type(observed) is not str):
        return False
    try:
        nodes = json.loads(expected)
        actual = json.loads(observed)
        if not isinstance(nodes, list) or not nodes:
            return False
        header = nodes[0]
        if (not isinstance(header, dict) or header.get('type') != 'text' or
                header.get('shopTitle') is not True or
                header.get('generatedBy') != 'INGEST_POST_PROCESS' or
                header.get('generatedRole') != 'SHOP_TITLE'):
            return False
        texts = header.get('texts')
        if (not isinstance(texts, list) or len(texts) != 1 or not isinstance(texts[0], dict) or
                texts[0].get('class') != 'title' or texts[0].get('content') != source_title):
            return False
        texts[0]['content'] = saved_title
        return canonical_json(nodes) == canonical_json(actual)
    except (ValueError, TypeError):
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
    if source and generated_title_readback_preserved(
            expected.get('descriptionJson'), observed.get('descriptionJson'),
            source_title=source.get('titleEn'), saved_title=expected.get('titleEn')):
        right['descriptionJson'] = left['descriptionJson']
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
