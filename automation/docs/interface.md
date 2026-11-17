# CLI / JSON interface v0.2.4

`python -m mye_c_automation` and `myec-automation` are the same entry.

| Command | Input | Output / effect |
|---|---|---|
| `doctor` | none | JSON resource, SIFT and confidence-policy diagnostics; no network |
| `fake` | `--scenario twin/frame/repair/keep`, optional `--data-root` | JSON Job ID, final business status, counters and report; synthetic only |
| `status JOB_ID` | optional `--data-root` | JSON frozen Job, state and automatic result; local read |
| `workflow -- ARGS` | existing runner arguments including explicit shop/PID, mode, site/model/policy configuration | existing runner Job/JSON output and complete evidence |
| `configure init` | optional `--directory` | Create only missing local config files; preserve user edits |
| `configure check` | optional `--directory`, paired `--shop` / `--pid` | Offline readiness and blockers; optionally generate, never execute, a read-only command |
| `models install-lama` | `--source`, `--destination`, `--sha256`, optional `--bind-config` | Checksum-pinned independent local copy; no download/inference or overwrite |
| `deploy review` | `--install-root`, `--output` | Local review manifest/helper; no user/ACL/service changes |

`doctor --config-dir DIR` combines resource checks with offline configuration checks. Readiness is explicitly configuration-only; neither a successful check nor a generated deployment review proves live read/write verification. Config initialization preserves `enabled=false` and `RIGHTS_UNKNOWN`. Image-options relative paths resolve from the config file location in every formal V2 entry.

Exit code 2 denotes CLI/configuration failure. Exit code 0 denotes command completion; inspect business state (`AUTO_VERIFIED`, `PARTIALLY_AUTO_FIXED`, `APPLY_UNKNOWN`, review, etc.). A completed command is not necessarily an accepted product. Unknown save recovery first reads; it does not resend.

All current image actions use the existing V2 plan/compiler/executor. The CLI adds no write bypass or model fallback. Low-level legacy modules remain for compatibility tests, not an alternative user workflow. Existing single-URL SKU writer capability is unchanged.

Programmatic integration uses `JobManager`, `workflow_runner.run_automatic`, a bound reader/writer, `JudgeClient` transport, and the existing `AutomationPolicy`. Tests demonstrate these contracts. No runtime integration imports test fixtures or Skill files.


`results JOB_ID --root JOB_ROOT` returns only final per-image JSON and REVIEW reason codes; raw responses/reasoning remain archived, never presentation. `cache-images JOB_ID --root JOB_ROOT [--cache-root DIR]` explicitly imports only sealed, SHA-verified image bytes into an independent success cache without changing the Job or calling a service. Runtime model/download settings and limits: runtime-tuning.md.


As of 0.2.4, image_concurrency accepts integers 1–10; the current local profile selects 10. New example profiles retain 2, and an omitted field retains serial compatibility. The bound applies to independent single-image V2 RECORD_ONLY audits; controlled budgets remain serial. Existing Jobs keep their frozen profiles.
