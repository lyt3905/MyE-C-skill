# V2.0 completion audit follow-up

Goal: complete missing local integrations and prove each requested requirement; preserve the full objective and keep real Shadow/Canary disabled.

Prior turn classification: no progress (status explanation only). Current evidence: HEAD 20ecfe83e307bbe15e7e298954a7c57d90dcdca6; 760-test historical local result, runtime adapter only injectable; SKU readback compares original URLs even when uploads remap them. No production readiness claim is supported.

- [x] Reproduce repaired-image SKU reference readback through the actual Fake executor, then fix comparison against the resolved expected snapshot and verify fetched candidate bytes.
- [x] Make the existing image-edit injection contract configurable from frozen Job image_options, with a pinned local adapter file, selected model and no new HTTP client or runner. Test load, budget, output and missing backend handling without real requests.
- [x] Verify suitability and existing-reference behavior in SKU selection; do not invent multi-image fields or SKU IDs.
- [x] Complete remaining local V2 1/3/10-product Fake regression and required semantic/mask scenarios; do not treat model fixtures as accuracy samples.
- [x] Re-run appropriate regression, compile and diff checks; publish requirement/evidence matrix, updated reports and continuation diff. Preserve prior logs and manifests as historical snapshots.

Evidence: full standard-entry regression 783/783, no failures/errors/skips, source unchanged. 23 retained Fake Jobs/1163 files. Added source-only SKU repair/deletion, same-save SKU remapping for deletions, last-box preservation and retained-byte drift checks. Full-audit CLI defaults to V2. Full objective remains active because real stages and their inputs are unproven; local completion is not substituted for the entire goal.

External gates remain: no real calls/writes this round; no approved usable LaMa model or real image-edit provider capability; no labeled V2 samples. These are not evidence of completed real phases. Do not mark the full goal complete while required evidence is missing.
