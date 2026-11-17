# Native archived-image re-audit

User requests5173 re-audit after prompt correction and previously requires direct program execution. The removed photos are absent from live input, so a reusable read-only snapshot input is necessary. Add audit-snapshot CLI as a thin adapter to existing JobManager/full-product V2 audit/JudgeClient/budget; do not create another classifier, runner, writer or budget system. No site read/save/upload/rollback, no restoration. Source account identity is historical, not a fresh login.

- [x] Verify a source V2 Job, its evidence manifest, product/account/PID/shop and in-directory image SHA bytes. Require current scoped policy and a fresh instruction. Reject output nested within source.
- [x] Implement sealed-snapshot reader/auditor feeding the existing run_full_audit; create a fresh audit-only Job/budget with current model/prompt, preserve source files and label historical origin. No remediation or title regeneration.
- [x] Add offline tests for native CLI flow/no site/write, source preservation/tamper, context mismatch and output overlap. Build/install0.2.21 and run all tests in isolated shards with exact ID coverage.
- [x] Run native audit-snapshot for original5173 source Job with current local model profile; report actual AI decisions for all original19 images including six deleted watermarked images. Retain failures/REVIEW as returned; do not change pixels or online references.
