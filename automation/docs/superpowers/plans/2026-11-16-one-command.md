# Single-command Workflow Implementation Plan

> Execute inline as a single agent under the user's continuous-execution instruction. No commits or delegation.

**Goal:** An installed program runs the full authorized product-image workflow from one URL command without Agent orchestration.

**Architecture:** Thin CLI/config entry delegates to the existing preflight and V2 runner. Extend that runner's ledger admission and independent reader hooks rather than copying report scripts.

**Tech Stack:** Existing Python 3.12+, unittest, packaged JSON policies, SQLite ledgers, Fake image/model/site adapters.

**Spec:** ../specs/2026-11-16-one-command-design.md

## Global constraints

Single agent; only automation/; preserve old evidence and dirty files; no git add/commit/push. No new real model or production calls for development. Tests never force REVIEW/unknown writes into success.

## Review focus

URL points to another backend; product override widens execution; API key leaks into output; prior partial write loses its evidence; a timeout causes a second save. Pin each in the owning tests.

## Task 1: Formal runner continuation and independent verification

- [x] Add red tests in tests/test_process_workflow.py for a fresh independent final reader and unchanged previous Job, known-partial continuation, and unknown-save readback with no duplicate save.
- [x] Extend ExecutionLedger with latest/register/directory lookup; keep default claim behavior.
- [x] Extend run_automatic with optional independent_reader_factory; automatically reconcile known partial writes using existing proof and restricted followup; record evidence into new directories. Test established callers unchanged.
- [x] Verify focused V2/ledger/preflight tests.

## Task 2: URL entry, config and durable operation result

- [x] Add red CLI tests for process URL, malformed/foreign URL, configured PID scope/rights, key file fallback, key restoration, audit-only, and resume binding.
- [x] Create one_command.py for input/config setup and delegation only; add process command in cli.py. Reuse model_config, configuration, JobManager, BudgetManager and run_automatic.
- [x] Include automatic exact-seven preflight, current-shop verification and new-login readback; record process invocation/result and progress, expose final JSON only.
- [x] Exercise complete Fake scenario through this same command with synthetic adapters and zero actual network/model/site writes.

## Task 3: Deliver and prove standalone execution

- [x] Document single-command setup, states, resume and per-product config; prepare PID5182-scoped local config from existing authorization without new writes.
- [x] Run full existing offline test discovery; fix demonstrated regressions, keep all original assertions.
- [x] Build/install version0.2.11 wheel; run complete command with source/Skill inaccessible and blocked real network.
- [x] Review implementation against spec, produce evidence/report and update project state; mark goal complete only after direct full-command evidence.

## Decisions / execution ledger

- Standing user instruction explicitly requires continuous execution without phase approvals; design/plan review is performed inline. Existing branch is already codex/*, and automation/ is untracked ongoing work: edit in place with pre-change file binding instead of a worktree that would omit it.

Final evidence: reports/one-command-20261116/acceptance.json; source1022/wheel1022, direct installed process CLI Fake and all preservation checks passed. No actual real validation or production-ready claim.
