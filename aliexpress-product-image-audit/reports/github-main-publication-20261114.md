# Main publication verification — 2026-11-14

Published scope: current aliexpress-product-image-audit code, tests, configuration examples, development reports and selected verification summaries. Other project changes, credentials, local configuration, raw product Jobs, image caches, SQLite ledgers and archives remain local.

Final local regression: **672 passed**, zero failures/errors. Full test status/log and source manifest are included beside this document. A standalone checkout does not include the private historical image/Job fixtures; historical replay requires those local artifacts. This is not a claim that all672 tests were re-run in a fresh clone.

Source binding: github-main-publication-source-manifest.json maps all tested source/test/config files to exact staged Git blob IDs and GitHub SHA256 values. Raw Windows hashes can differ because Git normalizes line endings; normalized contents are verified identical. The manifest excludes itself to avoid a circular hash.

Real read-only validation used earlier665/668 source snapshots:28 full-product calls plus2 SKU checks, aggregate30 requests/177351 gateway-reported tokens. No product upload/save/remediation occurred. Current672-source consensus patch was verified with local replay and Fake tests; not claimed as a new full real audit. Watermark/identity UNKNOWN and missing Shop7 templates remain unresolved. See mainflow-real-readonly-5097-20261114.md and sku-consensus-20261114.md.

Git base is current remote main; this publication contains no unrelated source-branch history. The automatic-development goal remains paused at the user's request. No further model calls were made for publication.
