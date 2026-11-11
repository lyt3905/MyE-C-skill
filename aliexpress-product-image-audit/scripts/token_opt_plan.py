# -*- coding: utf-8 -*-
"""Strict, network-free token-opt-v1 plan parser and validator."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PLAN_SCHEMA = "token-opt-plan/v1"
WORKFLOW_VERSION = "token-opt-v1"
POOLS = ("main", "detail", "sku")


class PlanError(ValueError):
    pass


def _object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PlanError(f"{where} must be an object")
    return value


def _list(value: Any, where: str) -> list[Any]:
    if not isinstance(value, list):
        raise PlanError(f"{where} must be an array")
    return value


def _keys(value: dict[str, Any], allowed: set[str], where: str, required: set[str] | None = None) -> None:
    unknown = set(value) - allowed
    missing = (required or set()) - set(value)
    if unknown:
        raise PlanError(f"{where} has unknown fields: {sorted(unknown)}")
    if missing:
        raise PlanError(f"{where} is missing fields: {sorted(missing)}")


def _image_ref(value: Any, where: str) -> None:
    item = _object(value, where)
    _keys(item, {"url", "asset"}, where)
    present = [key for key in ("url", "asset") if isinstance(item.get(key), str) and item[key].strip()]
    if len(present) != 1 or len(item) != 1:
        raise PlanError(f"{where} must contain exactly one non-empty url or asset")


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    _keys(plan, {"schema", "workflow_version", "pid", "shop", "precondition", "assets",
                 "desired", "post_actions", "approval", "review"}, "plan",
          {"schema", "workflow_version", "pid", "shop", "precondition", "desired"})
    if plan.get("schema") != PLAN_SCHEMA:
        raise PlanError(f"schema must be {PLAN_SCHEMA}; legacy plans are rejected")
    if plan.get("workflow_version") != WORKFLOW_VERSION:
        raise PlanError(f"workflow_version must be {WORKFLOW_VERSION}")
    if not isinstance(plan.get("pid"), int) or plan["pid"] <= 0:
        raise PlanError("pid must be a positive integer")
    if not isinstance(plan.get("shop"), int) or plan["shop"] <= 0:
        raise PlanError("shop must be a positive integer")

    pre = _object(plan["precondition"], "precondition")
    _keys(pre, {"state_sha256", "status"}, "precondition", {"state_sha256", "status"})
    if not isinstance(pre["state_sha256"], str) or len(pre["state_sha256"]) != 64:
        raise PlanError("precondition.state_sha256 must be a SHA256 hex digest")

    assets = _object(plan.get("assets", {}), "assets")
    for name, raw in assets.items():
        if not isinstance(name, str) or not name:
            raise PlanError("asset names must be non-empty strings")
        asset = _object(raw, f"assets.{name}")
        _keys(asset, {"local", "sha256", "min_short"}, f"assets.{name}", {"local", "sha256"})
        if not isinstance(asset["local"], str) or not asset["local"]:
            raise PlanError(f"assets.{name}.local must be non-empty")
        if not isinstance(asset["sha256"], str) or len(asset["sha256"]) != 64:
            raise PlanError(f"assets.{name}.sha256 must be a SHA256 hex digest")
        if "min_short" in asset and (not isinstance(asset["min_short"], int) or asset["min_short"] < 1):
            raise PlanError(f"assets.{name}.min_short must be a positive integer")

    desired = _object(plan["desired"], "desired")
    _keys(desired, {"images", "sku_image_assignments", "description", "fields"}, "desired")
    if not desired:
        raise PlanError("desired must declare at least one change")

    if "images" in desired:
        images = _object(desired["images"], "desired.images")
        _keys(images, set(POOLS), "desired.images")
        for pool, values in images.items():
            for idx, ref in enumerate(_list(values, f"desired.images.{pool}")):
                _image_ref(ref, f"desired.images.{pool}[{idx}]")

    for idx, raw in enumerate(_list(desired.get("sku_image_assignments", []), "desired.sku_image_assignments")):
        where = f"desired.sku_image_assignments[{idx}]"
        row = _object(raw, where)
        _keys(row, {"sku_id", "index", "expected_name", "expected_old_url", "image"}, where,
              {"expected_old_url", "image"})
        if "sku_id" not in row and "index" not in row:
            raise PlanError(f"{where} requires sku_id or index")
        if "index" in row and (not isinstance(row["index"], int) or row["index"] < 0):
            raise PlanError(f"{where}.index must be a non-negative integer")
        _image_ref(row["image"], f"{where}.image")

    if "description" in desired:
        desc = _object(desired["description"], "desired.description")
        _keys(desc, {"replace", "remove", "sync_shop_title"}, "desired.description")
        for action in ("replace", "remove"):
            for idx, raw in enumerate(_list(desc.get(action, []), f"desired.description.{action}")):
                where = f"desired.description.{action}[{idx}]"
                row = _object(raw, where)
                allowed = {"old_url", "expected_count", "image"} if action == "replace" else {"url", "expected_count"}
                required = allowed
                _keys(row, allowed, where, required)
                if action == "replace":
                    _image_ref(row["image"], f"{where}.image")
                if not isinstance(row["expected_count"], int) or row["expected_count"] < 1:
                    raise PlanError(f"{where}.expected_count must be a positive integer")

    if "fields" in desired:
        fields = _object(desired["fields"], "desired.fields")
        _keys(fields, {"titleEn", "brand", "identityJson", "weight"}, "desired.fields")
        if "titleEn" in fields and (not isinstance(fields["titleEn"], str) or not 1 <= len(fields["titleEn"]) <= 120):
            raise PlanError("desired.fields.titleEn must be 1..120 characters")
        if "identityJson" in fields and not isinstance(fields["identityJson"], dict):
            raise PlanError("desired.fields.identityJson must be an object")

    post = _object(plan.get("post_actions", {}), "post_actions")
    _keys(post, {"translate_title", "max_attempts"}, "post_actions")
    if post.get("translate_title") and "titleEn" not in desired.get("fields", {}):
        raise PlanError("translate_title requires desired.fields.titleEn")
    if "max_attempts" in post and post["max_attempts"] not in (1, 2):
        raise PlanError("post_actions.max_attempts must be 1 or 2")

    approval = _object(plan.get("approval", {}), "approval")
    _keys(approval, {"site_write"}, "approval")
    if "site_write" in approval and not isinstance(approval["site_write"], bool):
        raise PlanError("approval.site_write must be boolean")
    return plan


def load_plan(path: str | Path) -> dict[str, Any]:
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise PlanError("plan root must be an object")
    return validate_plan(plan)
