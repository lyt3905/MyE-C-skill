# -*- coding: utf-8 -*-
"""Safe token-opt-v1 executor. Dry-run is the default; live writes need two gates."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from description_refs import apply_exact_description_ops
from product_state import canonical_state_hash, diff_state, identity_object
from token_opt_plan import PLAN_SCHEMA, WORKFLOW_VERSION, PlanError, load_plan, validate_plan

ROOT = Path(__file__).resolve().parent


class ApplyError(RuntimeError):
    pass


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _update_run_metrics(workdir: Path, executor: dict[str, Any]) -> None:
    path = workdir / "run_metrics.json"
    try:
        metrics = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, TypeError, ValueError):
        metrics = {}
    if not isinstance(metrics, dict):
        metrics = {}
    metrics.setdefault("schema", "token-opt-metrics/v1")
    metrics["workflow_version"] = WORKFLOW_VERSION
    metrics["executor"] = executor
    _write_json(path, metrics)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _url(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("url")
    return str(value or "")


def _image_pools(product: dict[str, Any]) -> dict[str, list[str]]:
    images = product.get("images") or {}
    return {pool: [_url(item) for item in images.get(pool) or []] for pool in ("main", "detail", "sku")}


def _asset_paths(plan: dict[str, Any], plan_path: Path) -> dict[str, Path]:
    base = plan_path.resolve().parent
    paths: dict[str, Path] = {}
    for name, asset in plan.get("assets", {}).items():
        path = (base / asset["local"]).resolve()
        if os.path.commonpath([str(base), str(path)]) != str(base):
            raise ApplyError(f"asset {name} escapes product work directory")
        if not path.is_file():
            raise ApplyError(f"asset {name} not found: {path}")
        actual = _sha256(path)
        if actual != asset["sha256"]:
            raise ApplyError(f"asset {name} SHA256 mismatch: expected {asset['sha256']}, got {actual}")
        if "min_short" in asset:
            import cv2
            image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if image is None:
                raise ApplyError(f"asset {name} cannot be decoded")
            if min(image.shape[:2]) < asset["min_short"]:
                raise ApplyError(f"asset {name} short side {min(image.shape[:2])} < {asset['min_short']}")
        paths[name] = path
    return paths


def _resolve_factory(plan: dict[str, Any], paths: dict[str, Path], site: Any, upload: bool) -> tuple[Callable[[dict[str, str]], str], dict[str, str]]:
    uploaded: dict[str, str] = {}

    def resolve(ref: dict[str, str]) -> str:
        if "url" in ref:
            return ref["url"]
        name = ref["asset"]
        if name not in paths:
            raise ApplyError(f"unknown asset reference: {name}")
        if name not in uploaded:
            uploaded[name] = site.upload(str(paths[name])) if upload else f"pending-upload:{name}"
        return uploaded[name]

    return resolve, uploaded


def _find_sku(skus: list[dict[str, Any]], row: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    if "sku_id" in row:
        matches = [(idx, sku) for idx, sku in enumerate(skus)
                   if str(sku.get("skuId") or sku.get("id") or "") == str(row["sku_id"])]
        if len(matches) != 1:
            raise ApplyError(f"sku_id {row['sku_id']} matched {len(matches)} rows")
        idx, sku = matches[0]
    else:
        idx = row["index"]
        if idx >= len(skus):
            raise ApplyError(f"SKU index {idx} is out of range")
        sku = skus[idx]
    if "expected_name" in row and sku.get("skuName") != row["expected_name"]:
        raise ApplyError(f"SKU {idx} name drift")
    old = sku.get("skuImageUrl") or sku.get("imageUrl") or sku.get("image") or ""
    if old != row["expected_old_url"]:
        raise ApplyError(f"SKU {idx} image drift")
    return idx, sku


def compile_mutation(product: dict[str, Any], plan: dict[str, Any], resolve: Callable[[dict[str, str]], str]) -> dict[str, Any]:
    desired = plan["desired"]
    current_pools = _image_pools(product)
    final_pools = deepcopy(current_pools)
    if "images" in desired:
        for pool, refs in desired["images"].items():
            final_pools[pool] = [resolve(ref) for ref in refs]
    if not 1 <= len(final_pools["main"]) <= 6:
        raise ApplyError("final main pool must contain 1..6 images")
    if len(set(final_pools["main"])) != len(final_pools["main"]):
        raise ApplyError("final main pool contains duplicate URLs")

    skus = deepcopy(product.get("skus") or [])
    for row in desired.get("sku_image_assignments", []):
        idx, _ = _find_sku(skus, row)
        skus[idx]["skuImageUrl"] = resolve(row["image"])
    final_urls = set().union(*[set(values) for values in final_pools.values()])
    for idx, sku in enumerate(skus):
        url = sku.get("skuImageUrl") or sku.get("imageUrl") or sku.get("image")
        if url and url not in final_urls:
            raise ApplyError(f"SKU {idx} image is orphaned from final image pools")

    fields = desired.get("fields", {})
    if "weight" in fields and fields["weight"] != product.get("weight"):
        raise ApplyError("token-opt-v1 does not change weight; planned weight must equal current weight")
    old_identity = identity_object(product.get("identityJson"))
    new_identity = deepcopy(fields.get("identityJson", old_identity))
    if new_identity.get("logoCode", "") != old_identity.get("logoCode", ""):
        raise ApplyError("logoCode changes are forbidden")

    desc = product.get("descriptionJson")
    desc_counts: dict[str, int] = {}
    if "description" in desired:
        operations = deepcopy(desired["description"])
        operations["_titleEn"] = fields.get("titleEn")
        desc, desc_counts = apply_exact_description_ops(desc, operations, resolve)

    identity_payload = (json.dumps(new_identity, ensure_ascii=False, separators=(",", ":"))
                        if "identityJson" in fields else product.get("identityJson"))
    extra: dict[str, Any] = {
        "identityJson": identity_payload,
        "weight": product.get("weight"),
    }
    for key in ("titleEn", "brand"):
        if key in fields:
            extra[key] = fields[key]
    if desired.get("sku_image_assignments"):
        extra["skus"] = skus
    changed_images = {pool: final_pools[pool] for pool in desired.get("images", {})}
    return {
        "images": changed_images,
        "final_images": final_pools,
        "descriptionJson": desc,
        "description_changed": "description" in desired,
        "description_counts": desc_counts,
        "skus": skus,
        "extra": extra,
    }


def validate_preconditions(product: dict[str, Any], plan: dict[str, Any]) -> None:
    pre = plan["precondition"]
    if product.get("status") != pre["status"]:
        raise ApplyError(f"status drift: expected {pre['status']!r}, got {product.get('status')!r}")
    actual = canonical_state_hash(product)
    if actual != pre["state_sha256"]:
        raise ApplyError(f"state drift: expected {pre['state_sha256']}, got {actual}")


def _simulate(product: dict[str, Any], compiled: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(product)
    if compiled["images"]:
        images = deepcopy(result.get("images") or {})
        images.update(compiled["images"])
        result["images"] = images
    if compiled["description_changed"]:
        result["descriptionJson"] = compiled["descriptionJson"]
    result.update(compiled["extra"])
    return result


def verify_postconditions(before: dict[str, Any], after: dict[str, Any], compiled: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    expected = _simulate(before, compiled)
    translate_requested = bool(plan.get("post_actions", {}).get("translate_title"))
    if translate_requested:
        # Translation is server-generated and nondeterministic, but must be non-empty.
        expected["titleTranslationZh"] = after.get("titleTranslationZh")
    state_diff = diff_state(expected, after)
    # Formatting of the JSON string may change; compare its object meaning instead.
    state_diff.pop("identityJson", None)
    errors = [f"{key} mismatch" for key in state_diff]
    if identity_object(after.get("identityJson")) != identity_object(expected.get("identityJson")):
        errors.append("identityJson mismatch")
    if translate_requested and not str(after.get("titleTranslationZh") or "").strip():
        errors.append("titleTranslationZh is empty after requested translation")
    return errors


def execute_plan(site: Any, plan: dict[str, Any], plan_path: Path, *, apply: bool = False,
                 confirm_pid: int | None = None) -> dict[str, Any]:
    validate_plan(plan)
    workdir = plan_path.resolve().parent
    workdir.mkdir(parents=True, exist_ok=True)
    site.call("/api/admin/shops/current", {"shopId": plan["shop"]}, method="PUT")
    before = site.product(plan["pid"])
    validate_preconditions(before, plan)
    _write_json(workdir / "product_before.json", before)
    paths = _asset_paths(plan, plan_path)

    if apply:
        if confirm_pid != plan["pid"]:
            raise ApplyError("--confirm-pid must exactly match plan pid")
        if plan.get("approval", {}).get("site_write") is not True:
            raise ApplyError("plan approval.site_write must be true")

    resolve, uploaded = _resolve_factory(plan, paths, site, upload=apply)
    compiled = compile_mutation(before, plan, resolve)
    simulated = _simulate(before, compiled)
    planned_diff = diff_state(before, simulated)
    if apply and not planned_diff:
        raise ApplyError("apply plan compiles to no product changes")
    preview = {
        "schema": "token-opt-compiled/v1", "workflow_version": WORKFLOW_VERSION,
        "pid": plan["pid"], "dry_run": not apply, "state_before": canonical_state_hash(before),
        "changed_fields": sorted(planned_diff), "description_counts": compiled["description_counts"],
        "pending_or_uploaded_assets": uploaded, "compiled": compiled,
    }
    _write_json(workdir / "compiled_plan.json", preview)
    if not apply:
        _update_run_metrics(workdir, {
            "mode": "dry_run", "resolved_assets": len(uploaded), "upload_calls": 0,
            "site_save_calls": 0, "status_calls": 0, "translate_calls": 0,
            "post_write_readbacks": 0, "verification_ok": None,
        })
        return preview

    # Uploads can take time. Recheck the complete live state immediately before the only save.
    latest = site.product(plan["pid"])
    validate_preconditions(latest, plan)
    response = site.save(
        plan["pid"], images=compiled["images"] or None,
        desc=compiled["descriptionJson"] if compiled["description_changed"] else None,
        extra=compiled["extra"], expected_state_hash=plan["precondition"]["state_sha256"],
    )
    translate_receipts = []
    post = plan.get("post_actions", {})
    if post.get("translate_title"):
        attempts = post.get("max_attempts", 1)
        for _ in range(attempts):
            translate_receipts.append(site.call(
                f"/api/admin/products/{plan['pid']}/translate-title",
                {"titleEn": plan["desired"]["fields"]["titleEn"]}, method="POST"))
            probe = site.product(plan["pid"])
            if str(probe.get("titleTranslationZh") or "").strip():
                break
    after = site.product(plan["pid"])
    _write_json(workdir / "product_after.json", after)
    errors = verify_postconditions(before, after, compiled, plan)
    receipt = {
        "schema": "token-opt-apply-receipt/v1", "workflow_version": WORKFLOW_VERSION,
        "pid": plan["pid"], "save_response": response, "translate_receipts": translate_receipts,
        "uploaded_assets": uploaded, "state_after": canonical_state_hash(after),
        "verification_errors": errors, "ok": not errors,
        "rollback_source": "product_before.json",
    }
    _write_json(workdir / "apply_receipt.json", receipt)
    _update_run_metrics(workdir, {
        "mode": "apply", "resolved_assets": len(uploaded), "upload_calls": len(uploaded),
        "site_save_calls": 1, "status_calls": 0, "translate_calls": len(translate_receipts),
        "post_write_readbacks": 1, "verification_ok": not errors,
    })
    if errors:
        raise ApplyError("post-write verification failed: " + "; ".join(errors))
    return receipt


def create_plan_skeleton_from_product(product: dict[str, Any], pid: int, shop: int, path: Path) -> dict[str, Any]:
    plan = {
        "schema": PLAN_SCHEMA, "workflow_version": WORKFLOW_VERSION, "pid": pid, "shop": shop,
        "precondition": {"state_sha256": canonical_state_hash(product), "status": product.get("status")},
        "assets": {},
        "desired": {"fields": {"weight": product.get("weight")}},
        "post_actions": {"translate_title": False, "max_attempts": 1},
        "approval": {"site_write": False},
        "review": {"keep_summary": {}, "actions": []},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, plan)
    _write_json(path.parent / "product_before.json", product)
    return plan


def create_plan_skeleton(site: Any, pid: int, shop: int, path: Path) -> dict[str, Any]:
    site.call("/api/admin/shops/current", {"shopId": shop}, method="PUT")
    return create_plan_skeleton_from_product(site.product(pid), pid, shop, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Strict token-opt-v1 plan executor")
    sub = parser.add_subparsers(dest="command", required=True)
    p_validate = sub.add_parser("validate")
    p_validate.add_argument("plan")
    p_init = sub.add_parser("init")
    p_init.add_argument("pid", type=int)
    p_init.add_argument("--shop", type=int, default=7)
    p_init.add_argument("--out")
    p_run = sub.add_parser("run")
    p_run.add_argument("plan")
    p_run.add_argument("--apply", action="store_true")
    p_run.add_argument("--confirm-pid", type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            load_plan(args.plan)
            print("OK: token-opt-plan/v1 valid")
            return 0
        if args.command == "init":
            path = Path(args.out) if args.out else ROOT / "work" / f"pp_{args.pid}" / "plan.v1.json"
            snapshot = ROOT / "work" / f"pp_{args.pid}" / "audit_product.json"
            if snapshot.exists():
                product = json.loads(snapshot.read_text(encoding="utf-8"))
                create_plan_skeleton_from_product(product, args.pid, args.shop, path)
                print(f"{path} (reused audit_product.json; no network)")
            else:
                from site_client import Site
                create_plan_skeleton(Site(), args.pid, args.shop, path)
                print(path)
            return 0
        from site_client import Site
        site = Site()
        path = Path(args.plan)
        result = execute_plan(site, load_plan(path), path, apply=args.apply, confirm_pid=args.confirm_pid)
        print(json.dumps({key: result.get(key) for key in ("schema", "pid", "dry_run", "ok", "changed_fields")}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, PlanError, ApplyError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
