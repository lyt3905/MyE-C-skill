# -*- coding: utf-8 -*-
"""Fail-closed, exact-URL descriptionJson mutations for token-opt-v1."""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any


class DescriptionError(ValueError):
    pass


def parse_description(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise DescriptionError(f"descriptionJson is invalid JSON: {exc}") from exc
    else:
        value = deepcopy(raw)
    if not isinstance(value, (list, dict)):
        raise DescriptionError("descriptionJson root must be an array or object")
    return value


def _replace_exact(node: Any, old: str, new: str) -> int:
    count = 0
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if isinstance(value, str) and value == old:
                node[key] = new
                count += 1
            else:
                count += _replace_exact(value, old, new)
    elif isinstance(node, list):
        for value in node:
            count += _replace_exact(value, old, new)
    return count


def _remove_url_objects(node: Any, url: str) -> int:
    count = 0
    if isinstance(node, list):
        kept = []
        for value in node:
            if isinstance(value, dict) and value.get("url") == url:
                count += 1
                continue
            count += _remove_url_objects(value, url)
            kept.append(value)
        node[:] = kept
    elif isinstance(node, dict):
        for value in node.values():
            count += _remove_url_objects(value, url)
    return count


def _sync_shop_title(node: Any, title: str) -> int:
    count = 0
    if isinstance(node, dict):
        if node.get("generatedRole") == "SHOP_TITLE" and node.get("type") == "text":
            texts = node.get("texts")
            if not isinstance(texts, list):
                raise DescriptionError("SHOP_TITLE block has no texts array")
            for item in texts:
                if isinstance(item, dict) and item.get("class") == "title":
                    item["content"] = title
                    count += 1
        for value in node.values():
            count += _sync_shop_title(value, title)
    elif isinstance(node, list):
        for value in node:
            count += _sync_shop_title(value, title)
    return count


def apply_exact_description_ops(raw: Any, operations: dict[str, Any], resolve_image) -> tuple[str, dict[str, int]]:
    value = parse_description(raw)
    counts: dict[str, int] = {}
    for idx, row in enumerate(operations.get("replace", [])):
        new_url = resolve_image(row["image"])
        actual = _replace_exact(value, row["old_url"], new_url)
        if actual != row["expected_count"]:
            raise DescriptionError(f"replace[{idx}] expected {row['expected_count']} exact matches, got {actual}")
        counts[f"replace[{idx}]"] = actual
    for idx, row in enumerate(operations.get("remove", [])):
        actual = _remove_url_objects(value, row["url"])
        if actual != row["expected_count"]:
            raise DescriptionError(f"remove[{idx}] expected {row['expected_count']} URL objects, got {actual}")
        counts[f"remove[{idx}]"] = actual
    if operations.get("sync_shop_title"):
        title = operations.get("_titleEn")
        if not title:
            raise DescriptionError("sync_shop_title requires a planned titleEn")
        actual = _sync_shop_title(value, title)
        if actual < 1:
            raise DescriptionError("sync_shop_title found no SHOP_TITLE title nodes")
        counts["sync_shop_title"] = actual
    return json.dumps(value, ensure_ascii=False), counts
