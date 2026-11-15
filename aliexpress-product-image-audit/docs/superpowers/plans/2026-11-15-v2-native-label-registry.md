# Native legacy-label registry evaluation plan

> Execute inline, single agent, no commits or stage approvals (user instructions). Existing V2 spec and explicit reuse of Q01–Q24 govern this task.

Goal: make existing shadow_evaluate.py consume the actual v1.3 human-label registry, join observed predictions by SHA, and report labelled images still missing predictions. No new runner/client/ledger or new model/site requests.

Architecture: add one local registry-join helper and an optional --label-registry flag valid only with --v2. Retain existing scoring. Confirm image bytes, merge complementary same-SHA confirmations, import only explicit whole-image DELETE action truth. Inventory binary watermark labels without inventing five-action, packaging, SKU or repair outcomes. Never create a prediction for an unmatched label. Existing model/Description rules unchanged.

Review focus: Q19 duplicate SHA counts once; binary false is not KEEP; conflicting labels fail; missing predictions remain missing; action confirmation must not promote unconfirmed severe/repair/box/SKU outcomes. Synthetic predictions never count toward real gates.

- [x] Add failing tests for native action binding, partial labels, SHA duplicates/conflicts, image drift, unconfirmed outcomes, and CLI missing-output inventory/legacy-mode rejection.
- [x] Implement the helper and optional flag in the existing module; green related evaluation tests.
- [x] Run native CLI against the actual 47-label registry and existing 5-image result; preserve unknown accuracy when none match. Run complete offline regression once after source stabilizes.
- [x] Update reports, source bindings and applicable matrix; package a Git-generated incremental patch verified by applying only to temporary copies. Keep full goal incomplete until real gates are proved.
