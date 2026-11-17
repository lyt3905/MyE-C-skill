# Three bounded vision retries

User requested three retries for incomplete/extra-field model output. Preserve existing precise-watermark work. Keep10% print-region limit unchanged; explain its tradeoffs. Single agent/main, no Git publication or site writes.

- [x] Extend only the existing vision_retry_limit validation/Schema/client cap from0..1 to0..3. Three retries means initial+3, at most4 calls for a new image. Keep explicit lower attempt limits, protected-business/permanent-error no-retry rules, all raw responses and accounting.
- [x] Give eligible retries bounded Schema diagnostics (missing/extra fields and legal evidence IDs); do not fill/delete model output fields or change actions to bypass protection. Add red/green tests for fourth-call success, exhaustion, explicit lower caps and forbidden retries.
- [x] Set new config templates and active local model profile to3 with a local backup; do not change model/key/thinking/output/concurrency or other local values. Preserve old optional profiles and explicit0/1 semantics.
- [x] Retry only the3 preceding Schema failures in a new task. The failed originals already consumed their initial call: allow at most3 additional requests each, only while structurally retryable; stop at valid output. Valid REMOVE_TEXT can use current local repair/actual quality chain, at most2 quality calls each. No online product access/writes; seal sources and keep previous failures.
- [x] Full offline regression and independent wheel installation, bindings/package equivalence, real retry evidence and report. No cancellation of print protection limits.
