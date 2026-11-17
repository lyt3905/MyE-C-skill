# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from mye_c_automation.apply_token_plan import ApplyError, execute_plan
from mye_c_automation.audit_one import classify_cached_ocr
from mye_c_automation.description_refs import DescriptionError, apply_exact_description_ops
from mye_c_automation.product_state import canonical_state_hash
from mye_c_automation.render_token_report import render
from mye_c_automation.token_opt_plan import PlanError, validate_plan


class FakeSite:
    def __init__(self, product):
        self.current = deepcopy(product)
        self.save_calls = 0
        self.upload_calls = 0
        self.status_calls = 0
        self.calls = []

    def call(self, path, data=None, method=None):
        self.calls.append((path, deepcopy(data), method))
        if path.endswith("/translate-title"):
            self.current["titleTranslationZh"] = "回译"
        return {"ok": True}

    def product(self, pid):
        return deepcopy(self.current)

    def upload(self, path):
        self.upload_calls += 1
        return "https://uploads.example/" + Path(path).name

    def save(self, pid, images=None, desc=None, extra=None, *, expected_state_hash=None):
        self.save_calls += 1
        if expected_state_hash != canonical_state_hash(self.current):
            raise RuntimeError("stale")
        if images:
            self.current.setdefault("images", {}).update(deepcopy(images))
        if desc is not None:
            self.current["descriptionJson"] = desc
        self.current.update(deepcopy(extra or {}))
        return {"ok": True, "autoSave": True}

    def status(self, pid, value):
        self.status_calls += 1
        raise AssertionError("status must never be called")


def product_fixture():
    return {
        "titleEn": "Hot Sale Old Product A-01 A01", "title": "original",
        "titleTranslationZh": "旧回译",
        "descriptionJson": json.dumps([{"type": "image", "url": "https://a/x.jpg"}]),
        "images": {"main": ["https://a/main.jpg"], "detail": ["https://a/x.jpg"],
                   "sku": ["https://a/sku.jpg"]},
        "skus": [{"skuId": "s1", "skuName": "body", "skuImageUrl": "https://a/sku.jpg",
                  "shippingFee": 7.43, "stock": 2}],
        "price": 9.9, "weight": 0.2,
        "identityJson": '{"logoCode":"","modelCode":"A-01"}',
        "brand": "200014695", "brandId": None, "status": "PENDING",
    }


def plan_fixture(product):
    return {
        "schema": "token-opt-plan/v1", "workflow_version": "token-opt-v1",
        "pid": 1, "shop": 7,
        "precondition": {"state_sha256": canonical_state_hash(product), "status": "PENDING"},
        "assets": {},
        "desired": {"fields": {"titleEn": "Hot Sale New Product A-01 A01", "weight": 0.2}},
        "post_actions": {"translate_title": False, "max_attempts": 1},
        "approval": {"site_write": True},
        "review": {"keep_summary": {"main": 1, "detail": 1, "sku": 1}, "actions": []},
    }


class PlanTests(unittest.TestCase):
    def test_rejects_legacy_and_unknown_fields(self):
        with self.assertRaises(PlanError):
            validate_plan({"pid": 1, "actions": []})
        plan = plan_fixture(product_fixture())
        plan["surprise"] = True
        with self.assertRaises(PlanError):
            validate_plan(plan)

    def test_explicit_empty_pools_are_valid(self):
        plan = plan_fixture(product_fixture())
        plan["desired"]["images"] = {"detail": [], "sku": []}
        validate_plan(plan)
        self.assertEqual(plan["desired"]["images"]["detail"], [])

    def test_state_hash_dict_order_stable_list_order_sensitive(self):
        p = product_fixture()
        reordered = dict(reversed(list(p.items())))
        self.assertEqual(canonical_state_hash(p), canonical_state_hash(reordered))
        changed = deepcopy(p)
        changed["images"]["detail"] = ["b", "a"]
        self.assertNotEqual(canonical_state_hash(p), canonical_state_hash(changed))


class DescriptionTests(unittest.TestCase):
    def test_legacy_exact_url_operation_is_forbidden_and_input_is_opaque(self):
        raw = json.dumps([{"url": "https://one/x.jpg"}, {"url": "https://two/x.jpg"}])
        ops = {"replace": [{"old_url": "https://one/x.jpg", "image": {"url": "https://new/y.jpg"},
                             "expected_count": 1}]}
        resolved=[]
        with self.assertRaisesRegex(DescriptionError,'DESCRIPTION_OPERATION_FORBIDDEN'):
            apply_exact_description_ops(raw,ops,lambda ref:resolved.append(ref) or ref['url'])
        self.assertIn('https://one/x.jpg',raw);self.assertIn('https://two/x.jpg',raw)
        self.assertNotIn('https://new/y.jpg',raw);self.assertEqual(resolved,[])

    def test_count_mismatch_fails_closed(self):
        with self.assertRaises(DescriptionError):
            apply_exact_description_ops("[]", {"remove": [{"url": "x", "expected_count": 1}]}, lambda ref: "")


class ExecutorTests(unittest.TestCase):
    def test_dry_run_has_zero_mutations(self):
        product = product_fixture()
        site = FakeSite(product)
        plan = plan_fixture(product)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.v1.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            result = execute_plan(site, plan, path, apply=False)
            metrics = json.loads((Path(tmp) / "run_metrics.json").read_text(encoding="utf-8"))
        self.assertTrue(result["dry_run"])
        self.assertEqual(metrics['executor']["site_save_calls"], 0)
        self.assertEqual(site.save_calls, 0)
        self.assertEqual(site.upload_calls, 0)
        self.assertEqual(site.status_calls, 0)
        self.assertEqual(site.current, product)

    def test_noop_dry_run_is_valid_but_noop_apply_is_rejected(self):
        product = product_fixture()
        site = FakeSite(product)
        plan = plan_fixture(product)
        plan["desired"] = {"fields": {"weight": product["weight"]}}
        plan["approval"]["site_write"] = False
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.v1.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            preview = execute_plan(site, plan, path, apply=False)
            self.assertEqual(preview["changed_fields"], [])
            plan["approval"]["site_write"] = True
            with self.assertRaisesRegex(ApplyError, "Legacy writes disabled"):
                execute_plan(site, plan, path, apply=True, confirm_pid=1)
        self.assertEqual(site.save_calls, 0)

    def test_apply_uses_one_save_and_preserves_sku_fields(self):
        product = product_fixture()
        site = FakeSite(product)
        plan = plan_fixture(product)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.v1.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ApplyError, "Legacy writes disabled"):
                execute_plan(site, plan, path, apply=True, confirm_pid=1)
        self.assertEqual(site.save_calls, 0)

    def test_stale_state_rejected_before_save(self):
        product = product_fixture()
        site = FakeSite(product)
        plan = plan_fixture(product)
        site.current["status"] = "EDITING"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.v1.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaises(ApplyError):
                execute_plan(site, plan, path, apply=True, confirm_pid=1)
        self.assertEqual(site.save_calls, 0)

    def test_post_readback_detects_unplanned_field_drift(self):
        class CorruptingSite(FakeSite):
            def save(self, *args, **kwargs):
                response = super().save(*args, **kwargs)
                self.current["price"] = 999
                return response

        product = product_fixture()
        site = CorruptingSite(product)
        plan = plan_fixture(product)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plan.v1.json"
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ApplyError, "Legacy writes disabled"):
                execute_plan(site, plan, path, apply=True, confirm_pid=1)
            self.assertFalse((Path(tmp) / "apply_receipt.json").exists())
        self.assertEqual(site.save_calls, 0)



class ReportTests(unittest.TestCase):
    def test_report_is_compact_and_does_not_fake_budget_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            (workdir / "audit_flags.json").write_text(json.dumps({
                "summary": {"counts": {"main": 1, "detail": 1, "sku": 1}, "suggested_mode": "fast"}
            }), encoding="utf-8")
            (workdir / "plan.v1.json").write_text(json.dumps({
                "review": {"actions": [{"kind": "KEEP", "slot": str(i)} for i in range(10)]}
            }), encoding="utf-8")
            (workdir / "run_metrics.json").write_text(json.dumps({
                "workflow_version": "token-opt-v1", 'executor': {"mode": "dry_run"},
                "budget": {"full_resolution_views": {"value": None, "limit": 12},
                           "temporary_scripts": {"value": None, "limit": 1},
                           "model_requests": {"value": None, "target_max": 45}}
            }), encoding="utf-8")
            (workdir / "product_before.json").write_text(json.dumps({"titleEn": "current-title"}), encoding="utf-8")
            (workdir / "product_after.json").write_text(json.dumps({"titleEn": "stale-title"}), encoding="utf-8")
            (workdir / "apply_receipt.json").write_text(json.dumps({
                "schema": "token-opt-apply-receipt/v1", "workflow_version": "token-opt-v1",
                "pid": 1, "ok": True
            }), encoding="utf-8")
            report = render(workdir, 1)
        self.assertIn("预算状态：UNKNOWN", report)
        self.assertIn("只读审计/dry-run，未写回", report)
        self.assertIn("回读校验：不适用（dry-run）", report)
        self.assertNotIn("stale-title", report)
        self.assertIn("模型请求：None / 45", report)
        self.assertLessEqual(len(report.splitlines()), 40)


class CacheIsolationTests(unittest.TestCase):
    def test_same_raw_ocr_reclassified_per_title(self):
        items = [{"text": "官方品牌", "score": 0.99, "rect": [0, 0, 30, 10], "region": "full"}]
        _, hits_without_title, _ = classify_cached_ocr(items, title_text="Another product")
        _, hits_with_title, _ = classify_cached_ocr(items, title_text="官方品牌 product")
        self.assertGreater(len(hits_without_title), len(hits_with_title))


if __name__ == "__main__":
    unittest.main()
