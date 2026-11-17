# Local desktop interface follow-up

The real-readonly stage is still missing credentials and separate authorization. Continue the previously identified software-interface gap locally: configuration forms, offline checks, Fake task progress, Job browsing and before/after image comparison. No live model/site action is invoked by the interface in this stage.

Use Python's installed Tkinter and the existing Pillow dependency. Keep a desktop UI, not a hosted service. All task execution delegates to the existing CLI through a background subprocess; do not create another workflow/client/ledger. A GUI worker may execute only configure-check and Fake commands. Real-readonly command preparation remains explicit and execution stays outside this local interface until independently authorized.

- [x] Add tests for command delegation, configuration editing without credential leakage or authorization changes, conflict detection, Job listing, status display and byte-bound image comparison paths.
- [x] Implement GUI data helpers around current config/Job files and one nonblocking CLI subprocess bridge.
- [x] Add desktop window with Chinese configuration/checks, Fake scenario controls, task progress/history and before/after previews. Mask password/key fields; keep API key in memory only.
- [x] Add ui CLI/Windows launcher, launch a local window and verify Tk controls/Fake completion automatically. No network requests or real model inference.
- [ ] Native mouse/visual inspection: blocked by Windows lock screen; no unlock/bypass attempted.
- [x] Build a distinct versioned wheel; verify original-source-free installation, full inherited tests and new UI tests. Preserve previous 0.2.0 evidence.

Ruling: The broad request is to fill the previously identified missing capabilities. After core CLI/resources completion, use the waiting period to implement its subsequent local interface priority. The optional scope question has no submitted response; no response is treated as approval for real operations. If the user explicitly chooses CLI-only, respect that steering.
