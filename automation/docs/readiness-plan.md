# Local readiness completion plan

Goal: Close the identified configuration, resource and deployment-tool gaps while retaining the migrated V2 engine.
Baseline: repository HEAD 68e168f; existing automation extraction and all user modifications preserved. Source Skill remains read-only. Single agent, no staging/commits/pushes, no real model requests or online product operations.

Design: Add configuration/bootstrap and offline readiness commands around the existing validators, model loader and workflow. Keep one runner/client/compiler/executor. Keep authorization disabled and image rights UNKNOWN until explicitly configured. Do not silently discover credentials or carry over old Jobs. Existing trained weights may be copied locally by an explicit checksum-pinned installer; never bundle them in the wheel.

- [x] Snapshot current automation source/config/tests and Git differences into a new follow-up evidence directory.
- [x] Pin tests for REPLACE_TWIN authorization in the shipped example and the actual formal planner, packaged legacy template availability, configuration bootstrap without overwrite, readiness checks, and model copy/checksum/no-overwrite behavior.
- [x] Add init/check configuration CLI using the existing validators, relative paths bound to the configuration directory, and redacted results. Check accounts/model key/weights without connecting to services. Generate explicit future audit commands; do not execute them.
- [x] Install the original template as a checksummed program asset, retain its provenance, and correct its example path. V2 semantics remain AI-only.
- [x] Add checksum-pinned local model installation and model-options binding; install an independent local copy of the existing LaMa weights without running trained inference.
- [x] Port the original Windows deployment review helper and expose a local review workflow; no account, ACL or service mutation. Add an easy launcher and current deployment/operation documentation.
- [x] Run relevant tests, then full unchanged discovery plus new tests and wheel isolation with original/new source directories inaccessible. Keep new evidence separate from previous acceptance.
- [x] Produce a concrete real-readonly verification proposal, with real write verification separately gated. Missing credentials/authorization remain explicit NOT_RUN, never Fake-as-real.

Review focus: default REPLACE_TWIN permission; wheel assets and source-free paths; no automatic credential lookup; hash mismatch leaves no partial installation; config init never overwrites user files; offline doctor never logs passwords/keys or accesses services; review tooling must not imply production activation.

Scope note: User was asked asynchronously whether to include a graphical interface. Continue independent configuration/resources work while waiting. The previously suggested priority is CLI/runtime completion first; graphical management is a subsequent enhancement unless the user selects it now.
