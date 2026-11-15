# V2 offline evaluation preparation

Previous goal turn: progress (23 regression additions, real integration fixes, 783 passing tests and retained Fake evidence). Full objective remains active; real stages are not authorized.

Audit evidence: existing shadow_evaluate.quality_metrics accepts binary truth/prediction, groups by business position and identifies samples by caller IDs. It cannot directly score five actions, preserve UNKNOWN box status or enforce independent SHA counts across positions. Extend this existing offline tool; do not create a second evaluator runner, model client, ledger or site writer.

- [x] Add failing tests for independent SHA deduplication/conflicts, five actions and REVIEW, real/synthetic provenance, actual image-byte binding, per-action severe errors, repair outcomes, box directional confusion, SKU group scores and missing labels/thresholds.
- [x] Implement V2 scoring in shadow_evaluate.py with a CLI option; use only local JSONL/files and never call models or a site. Keep binary evaluation compatibility. Unknown usage/cost and missing labels must not become zero or success.
- [x] Generate an empty real-label dataset template and NOT_EVALUATED report, plus synthetic examples explicitly separated from real gate evidence.
- [x] Run targeted and standard regression, preserve existing logs, update reports/requirement matrix and diff/source bindings. Keep full goal active while real authorization, independent labels and runtime capabilities remain missing.
