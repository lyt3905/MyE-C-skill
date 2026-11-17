# DeepSeek title integration implementation plan

**Goal:** Add reference-folder title generation to the existing product workflow, with one combined restricted save and independent readback.

**Reference:** Only `aliexpress-product-image-audit/title-rewriter/` supplies title business rules. The reference folder remains read-only; the installed software owns its prompt and has no runtime dependency on that folder.

**Architecture:** Reuse the reference `make_messages`/`parse_result` contract and prompt, with the existing JudgeClient, BudgetManager, V2 compiler, executor and verifier. Do not use the legacy deterministic title generator. The source reference generates content only, so this integration changes `titleEn` only: modelCode is recorded, no brand/identity mutation or Chinese back-translation. Warnings defer the title while images continue. First valid response wins; bounded retries default to2 independently of image retries. Unknown usage remains null. No confidence gate or additional model review.

**Configuration:** Existing `allow_actions.TITLE_REWRITE` explicitly enables the stage. Existing configurations remain valid and image-only until enabled. A `title_rewrite` policy section configures retry count/delay. New example keeps this write permission disabled; documentation explains enabling it for an authorized product. The read-only command generates/reports when enabled without saving. Existing main-count preflight remains independent; the following image/title plan saves at most once.

**Verification:** Raw responses and calls retained in Job; successful generation reused within the same frozen Job without another request. A title candidate binds source snapshot, prompt, request settings and original raw response. Compiler verifies that binding instead of calling deterministic rewrite rules. Independent readback must match the approved title and keep all other business fields protected. Old jobs without a title stage remain valid.

- [x] Add failing unit tests for sanitized input, output contract, first-success/retries/cache/raw retention and warning deferral.
- [x] Package the exact reference prompt and implement title adapter through the existing model client/ledger.
- [x] Add title candidates to V2 preparation and the existing compiler; retain legacy behavior for legacy jobs.
- [x] Verify title in independent V2 readback and expose final-only title results in `process`/read-only output.
- [x] Add opt-in Fake CLI and formal process tests for combined save, no translation/identity changes, warnings/failure, permission disabled and unknown-save recovery.
- [x] Run targeted/full offline regressions and installed-wheel independence checks. No real model/site calls, no commit/push for this task.
