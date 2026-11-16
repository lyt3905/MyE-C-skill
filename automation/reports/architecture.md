# Independent software architecture

Baseline: 68e168f1a08c6338cb0964dffbd021bb5e484556, 2026-11-16.

The src-layout package namespaces existing modules without redesigning V2. This retains mature responsibility boundaries and avoids a second runner, model client, plan compiler, executor or ledger.

| Responsibility | Existing migrated module |
|---|---|
| Stable CLI/JSON and diagnostics | `cli`, `resources`, `paths` (new orchestration) |
| Job lifecycle and workflow | `job_manager`, `workflow_runner`, `full_product_audit` |
| Product read and write adapters | `site_client`, `executor.site_write_client` |
| Model requests, cache, usage | `ai_judge.client`, `budget_manager`, `token_budget` |
| V2 visual contract | `ai_judge.image_action_decision`, `ai_judge.image_quality_v2` |
| Same-photo geometry and dense pixels | `visual_versions` |
| Description body and SHA content groups | `description_images`, `image_content_plan` |
| V2 remediation and SKU selection | `v2_remediation`, `sku_assignment`, `image_repairs_v2` |
| Restricted plan and execution | `plan_compiler`, `plan_v2`, `executor.local`, `executor.service` |
| Independent readback and reporting | `v2_remediation.verify_content`, `automatic_report` |
| Global coordination | `account_coordination`, `execution_ledger`, `upload_rate` |
| Offline demo adapters | `fake` (calls the same runner, no business decisions) |

Package configuration and prompts are read-only wheel resources. Writable data is independent. Archived contract helpers remain explicitly for regression compatibility; the CLI's V2 path does not select them. No SOP is loaded: the one title translation table used by legacy tests was extracted as a package-owned technical data resource.

Real models, external editing services, online writes and platform deployment are NOT_RUN. Trained LaMa weights are an optional, explicitly pinned external resource.
