# Deferred desktop draft — not part of current delivery

The user explicitly chose CLI/runtime completion first and desktop UI in a later round. This directory preserves the prematurely implemented draft and its nine tests, unchanged, for that later round. It is outside src/, the active test suite and the formal wheel.

The draft is not installed, not a supported command and not a current launcher. Do not run its gui.cmd directly here: its original project-relative paths need reviewed reintegration in the future stage. No original V2/business tests were removed or weakened; the current CLI suite retains all 953 pre-desktop tests and adds delivery-scope checks. Historical 962-test desktop evidence remains under reports/ui-20261116 and is not rewritten as current CLI evidence.

Draft file move paths and SHA256 are recorded in reports/cli-scope-20261116/move-plan.json. Current supported version is CLI 0.2.1. The previous 0.3.0 wheel is a deferred experiment, not the selected delivery artifact.
