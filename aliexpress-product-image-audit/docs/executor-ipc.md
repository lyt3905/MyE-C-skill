# Windows executor IPC

Run `python -m executor.ipc serve CONFIG.json` under a dedicated Windows account.
Run `python -m executor.ipc request REQUEST.json --server-sid S-1-5-21-SERVER --address \\.\pipe\ae-audit-NAME` from the authorized client.
Requests contain `plan`, optional `ticket`, and `dry_run` (default true). There is no signing or shutdown endpoint. Tickets must be issued by a separate trusted approval process using the protected HMAC key.

Minimal offline config (absolute paths):
```json
{"address":"\\\\.\\pipe\\ae-audit-demo","client_sid":"S-1-5-21-REPLACE","secret_file":"C:\\protected\\key.bin","nonce_database":"C:\\protected\\nonce.db","evidence_root":"C:\\protected\\evidence","fake":true,"write_log":"C:\\protected\\fake-writes.log","enable_writes":false,"max_requests":100}
```
Use the actual SID from `whoami /user`. Key must contain at least 32 random bytes. Fake mode never imports the site client or accesses the network. `enable_writes:true` allows signed fake saves for testing; requests still require a valid bound one-use ticket.

Production requires `fake:false`, explicit `server_sid`, `credentials_file` and TLS verification. The host performs the read-only deployment inspection below before importing the site writer. The review-only deployment script changes no accounts, ACLs or services. Never enable writes on a shared-account installation. Tickets remain mandatory for writes. Uploads use a random request-scoped snapshot directory inside the protected evidence root, containing exactly the bytes whose hashes were checked; original paths are never reopened for upload. Snapshots are cleaned after each request.


Transport only uses JSON byte messages, at most 65536 bytes, with a 5-second request/response read deadline. The accept loop waits for clients; stop the host process to stop serving. Invalid requests return a generic rejection without secrets. Host process startup/config errors fail closed. Windows pipe name must start `\\.\pipe\ae-audit-`. First-instance flag prevents quietly attaching to a competing server. The client requires an expected server SID and verifies the actual named-pipe server process token SID before sending any request.

Offline check: `PYTHONPATH=scripts python -m unittest discover -s tests -p test_ipc.py`. The subprocess integration test sends no-ticket, changed-plan, dry-run, signed save, and replay requests, asserting zero writes before approval and exactly one save afterwards. No production account, ACL, service, credentials or site is modified.

Read-only deployment gate (required for production): set explicit `server_sid` distinct from `client_sid`, then run `python -m executor.deployment_preflight CONFIG.json` under the actual service account. The JSON report includes inspected owners/current SID and concrete blocking paths/ACEs; exit 2 means deployment is blocked. The production host repeats this inspection at startup; `deployment_verified` is no longer accepted as proof. Config, key, credentials, nonce database and evidence directory must already exist at absolute paths. Ancestors and code/evidence descendants are inspected, and untrusted write-capable ACEs or owners and reparse points block startup. No test file is created and no ACL is changed. SYSTEM, Administrators and the service SID are the only permitted writers; administrators remain trusted deployment operators. Client/Agent must not hold administrator privileges or access another trusted writer's token. This last account-isolation requirement still needs an independent administrator review; a DACL scan cannot prove the absence of stolen credentials or elevated processes.
