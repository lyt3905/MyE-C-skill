# Model-directed images implementation plan

**Goal:** DeepSeek owns image content, attributes and action decisions; the existing program executes model instructions and fixed business/technical checks.

**Architecture:** Keep the existing V2 auditor, compiler, repairs, model client, SKU selector and writer. Formal decide stops calling geometric/role policy overrides and stops converting explicit actions to REVIEW because class/owner/box status is unknown. Model region instructions are optional for historical compatibility, requested for all new calls; explicit region KEEP/REMOVE_TEXT controls mask interpretation. Pixel masking and same-photo geometry are execution algorithms, not semantic classifiers.

**Constraints:** Single agent; current dirty checkout preserved; no git add/commit/push; no new real model/site calls or product writes. Historical Jobs/raw responses/ledgers/fixtures byte-exact. Existing fixed rules remain: exact-seven preflight, dimensional/format/schema/account/evidence/rights validation, nonempty required pools, existing SKU one-URL binding/box grouping/distinct-photo fallback, retained packaging evidence, same-photo replacement priority, pixel protection, AI quality review and independent byte readback. Explicit REVIEW/abstain/errors remain unresolved.

**Ruling:** User already requested continuous single-agent execution without stage approvals; implement locally without another design approval. Existing framework and working tree are required, no third runner or clean-up refactor.

## Tasks
- [x] Snapshot current source/tests/fixtures and Git baseline in a fresh report directory.
- [x] Add regressions: raw DELETE with UNKNOWN attributes executes; KEEP with store roles remains KEEP; explicit REVIEW/abstain/missing output never becomes success; explicit per-region actions control execution; SKU attributes override class whitelist; AI KEEP clean candidates are not locally reclassified; public Fake delete aliases/body/SKU save+readback.
- [x] Run new tests red, implement only the model decision boundary, schema/prompt, SKU filters, candidate eligibility and formal reassessment call removal.
- [x] Update outdated behavior-specific test expectations with explicit new user rule and preserve negative tests; run complete offline discovery, record all failures/errors/network and unchanged bindings.
- [x] Build/install new version and verify packaged files, update current-state and user docs. Report local/fake verification separately; 5180 and other online products unchanged this task.

**Review focus:** region instructions vs protected coordinate overlap; UNKNOWN attributes vs explicit REVIEW; SKU missing packaging vs class aliases; no historical audit replay; successful raw KEEP is not silently converted to repair/delete. All are covered by the new focused tests and existing full suite.

Final evidence: reports/model-directed-images-20261117/acceptance.json. 1081 complete tests,10 new tests and16 focused installed-package checks pass; no real network/model/product actions.
