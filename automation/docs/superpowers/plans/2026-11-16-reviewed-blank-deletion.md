# Apply the user's review without unrelated image changes

User decisions: keep PID5185 main2 as generic product information independent of a shop; delete the three confirmed1x1 blank GIF detail slots (5187/detail20,5186/detail7,5185/detail17). This authorizes only these actual reference deletions and necessary saves/readback. No new models, no other image/SKU edits, no original evidence rewrites, no commits, single agent.

Observed blocker: current main counts8/7/7. The existing whole-product main-count check rejects even an exact one-slot detail-only deletion. Do not remove unrelated main photos or disable the normal six-image rule to satisfy the checker.

Implementation: add a narrow reviewed_detail_deletions V3 post-action, compiled from current state, actual freshly verified1x1 GIF bytes, explicit user review, job/account/snapshot hashes. Executor rechecks bound proof/bytes before writes. Pure final-state validation permits only the exact approved detail deletions with unchanged existing main overflow; records the preexisting count as a warning and never claims whole-product verification. Standard plans still reject excess main count. Existing ExecutorService, LocalExecutor, live preview and execution ledger perform the save. Ordinary product photos cannot enter the blank channel. Protect all main/SKU/description/other fields.

- [x] Add red tests for7/8 main counts, unchanged scope, unreviewed/photo/tamper rejection and no repeated unknown save.
- [x] Implement reviewed_images compiler/proof check plus strict plan/schema/validator/executor integration.
- [x] Run current full regression and standalone installed verification; retain original assertions.
- [x] Prepare fresh bounded Jobs for the3 approved deletions, replay source evidence only for binding, and preserve the new humanKEEP separately from original model replies.
- [x] Execute once per product after final checks, independently verify retained bytes/state and the kept main2, and report actual saves/uploads/model requests.

This is a targeted partial-save capability, not a claim that7/8 main images meet the full audit requirement. No global configuration or main-image actions are enlarged.

Final: source/wheel1036 passed;3 authorized live saves,0 uploads/models; kept main2 exact;114 pool/SKU/body byte positions verified. All historical sources preserved. Supplemental body readback executed separately, general integration not claimed.
