# Generic Watermark Processing Module Implementation Plan

**Goal:** Finish Phase 1–7 of the two supplied watermark module specifications using the actual existing V2 chain.

**Architecture:** Add a product-independent execution API with validated V2-compatible regions, local ROI planning, configurable OpenCV/LaMa routing and deterministic receipts. Reuse existing Mask/region semantics, TorchScript adapter, quality inspector, client, Plan and Job flow. Delegate explicit REGION inputs from existing remove_text; preserve older glyph modes without expanding them.

**Tech Stack:** Python3.12, Pillow, installed OpenCV/NumPy/Torch and pinned local LaMa. No new models or dependencies.

**Spec:** ../../通用水印处理模块_开发任务书_V1.0.md and ../../Codex执行目标_通用水印处理模块.md

## Global constraints

Single agent; automation-only edits; preserve all existing modifications/tests/evidence; no git add/commit/push; no real DeepSeek or site operations. Confidence RECORD_ONLY. No OCR/new template detector/MAT/Stable Diffusion. Input has no product/shop/SKU/Description fields. Existing REPLACE_TWIN and action rules remain.

## Review focus

- Self-intersecting polygons, duplicate instance IDs, ambiguous path/bytes and mismatched SHA must block before inference.
- Same group but distant instances must remain separate; neighboring distinct groups must not merge, all union masks remain sparse.
- Alpha, overlapping masks and future instances must survive ROI fusion without damage outside union.
- Engine exceptions, unchanged/corrupt output or source mutation must not become successful candidates or uploads.
- Model identity/unknown failures must not trigger retry; permitted feedback allows one alternate algorithm only, always starting from original.

## Phase 1 (audit completed before implementation)

- [x] Inspect client, prompts/schema, REMOVE_TEXT/Plan, Mask, OpenCV, LaMa, quality/cache and working tree.
- [x] Write reports/watermark-module-audit.md and reports/lama-environment-check.md; bind Skill inventory and git diff; verify installed weight bytes.

## Phase 2 (contract)

- [x] Add tests/test_watermark_module.py for path/bytes binding, status/schema, coordinate/authorization/semantic preservation and rejection cases; observe RED.
- [x] Create watermark_processing/contracts.py and package schemas using current V2 mark schema (optional ID/group/layout/content metadata), not a competing business classifier.
- [x] Write reports/watermark-module-contract.md and document Python API and output statuses.

## Phase 3 (regions/masks)

- [x] Red/green tests for eight arrangements, varied angles/content/colour/opacity, self-intersections, adjacency/groups, ROI area/context, protected regions and sparse union.
- [x] Implement WatermarkRegionManager and WatermarkMaskBuilder using current mask_for and mark_disposition; retain independent masks/IDs/ROIs, no semantics inferred.

## Phase 4 (execution)

- [x] Red/green tests for configurable routing, crop-local adapter calls, exact fusion/alpha, multiple batches, backend failures and new-file output.
- [x] Implement RepairRouter/InpaintingEngine around installed OpenCV and existing LaMa callable. Only small/simple/nonoverlap/nontransparent use Telea; NS explicit fallback; complex/large/transparent use LaMa.
- [x] Run pinned actual LaMa locally across varied generated samples, store full inputs/observations/masks/outputs/runtime and side-by-side views, no real model API.

## Phase 5 (quality/fallback)

- [x] Red/green tests for output SHA/mask corruption/source mutation/outside-mask changes and incomplete/identity-damaged model feedback.
- [x] Implement module QualityChecker and normalized result; PENDING_AI_REVIEW until existing inspector approves; no module-owned retry/client.

## Phase 6 (integration)

- [x] Red/green native Fake tests for multi-instance repair/upload/save/readback, denied rights, protected print, model residual/identity/unknown decisions and bounded alternate.
- [x] Delegate explicit REGION remove_text through module; pass configured policy; lazy-load LaMa only when selected. Existing legacy glyph route stays compatible.
- [x] Existing inspector receives original observation, source/candidate and mask preview. Annotate module status with bound AI quality without rewriting raw replies.

## Phase 7 (acceptance)

- [x] Full offline suite, exact test-ID coverage and source binding; wheel package/source identity and isolated installed API/Fake tests.
- [x] Verify no original Skill/diff changes; produce all required reports, dependency/API documentation, image comparisons and masks.
- [x] Audit each taskbook requirement against concrete evidence; distinguish IMPLEMENTED/FAKE_VERIFIED/local REAL_MODEL_VERIFIED and real DeepSeek NOT_RUN; list limitations. No online production-ready claim.

User explicitly requested continuous Phase1–7 execution; no intermediate approval gates, subagents or commits.

## Completion ledger

Phase1 audit preceded implementation; phase2 missing API tests RED15→GREEN; integration RED5→GREEN; trace/cache RED→GREEN; nested Mask limit RED→GREEN; Plan receipt tamper RED→GREEN. Full0.2.27 regression exposed blank-background overclassification in new module; added failing boundary test, removed only new content judgment, retained existing V2 blank-image gate, preserved all old tests. Final0.2.28 suite1155+isolated31 pass;14 sample cases/34 actual LaMa calls and dual-SKU Fake AUTO_VERIFIED preserved. Ruling: legacy glyph supplementation stays in existing full-frame contract, while new explicit REGION supplementation uses local module and bound inherited-mask geometry; avoids breaking mature path or introducing template identification into the generic module. Real DeepSeek/online remain NOT_RUN as taskbooks explicitly require by default. All reports and artifacts verified; no production-ready claim.
