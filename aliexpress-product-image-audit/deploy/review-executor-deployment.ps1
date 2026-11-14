# Review-only deployment plan. This script does NOT change accounts, ACLs or services.
param([Parameter(Mandatory)][string]$ServiceAccount,[Parameter(Mandatory)][string]$ClientSid,[string]$Root='C:\ProgramData\AEImageExecutor')
$ErrorActionPreference='Stop'
if ($ClientSid -notmatch '^S-1-5-(\d+-)*\d+$') { throw 'ClientSid must be a Windows SID' }
$account = New-Object System.Security.Principal.NTAccount($ServiceAccount)
$serviceSid = $account.Translate([System.Security.Principal.SecurityIdentifier]).Value
Write-Output "REVIEW ONLY: dedicated account $serviceSid; client $ClientSid; protected root $Root"
Write-Output "Administrator must create a dedicated non-admin service account and copy reviewed code plus interpreter into the protected root."
Write-Output "Proposed root ACL: SYSTEM and Administrators full; service account modify; remove inherited and other access."
Write-Output "Proposed code/interpreter ACL: service account read/execute only; administrators write; client/Agent no write."
Write-Output "Config, credential and HMAC key ACL: SYSTEM/administrators plus service account read; client/Agent no access."
Write-Output "Nonce database parent: service account modify; client/Agent no access. Never reset nonce state or reuse keys."
Write-Output "Evidence staging: client write, service read; service copies and hashes approved evidence into protected root before issuing tickets."
Write-Output "Run under dedicated account: python -m executor.ipc serve <protected-config.json> with protected scripts on PYTHONPATH."
Write-Output "Keep enable_writes false until independent ACL, identity and CA validation are complete. No commands were executed."
