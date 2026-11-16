# Review-only provisioning. This file does not create users or change ACLs.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ExecutorAccount,
    [Parameter(Mandatory=$true)][string]$AgentAccount,
    [Parameter(Mandatory=$true)][string]$InstallRoot,
    [Parameter(Mandatory=$true)][string]$OutputPath
)
$ErrorActionPreference = 'Stop'
if ($ExecutorAccount -eq $AgentAccount) { throw 'Executor and agent must use distinct accounts' }
foreach ($value in @($ExecutorAccount,$AgentAccount)) {
    if ($value -notmatch '^[A-Za-z0-9_.\\-]+$') { throw 'Invalid account name' }
}
$root = [IO.Path]::GetFullPath($InstallRoot)
if ($root -eq [IO.Path]::GetPathRoot($root)) { throw 'InstallRoot must not be a drive root' }
$executorSid = ([Security.Principal.NTAccount]$ExecutorAccount).Translate([Security.Principal.SecurityIdentifier]).Value
$agentSid = ([Security.Principal.NTAccount]$AgentAccount).Translate([Security.Principal.SecurityIdentifier]).Value
if ($executorSid -eq $agentSid) { throw 'Accounts resolve to the same SID' }
if (Test-Path -LiteralPath $root) {
    $node = Get-Item -LiteralPath $root -Force
    while ($null -ne $node) {
        if (($node.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Reparse point in deployment path' }
        $node = $node.Parent
    }
}
# Output a reviewable manifest only. Credentials must be provisioned separately by an administrator.
$manifest = [ordered]@{
    schema = 'executor-deployment-review/v1'
    write_enabled = $false
    server_sid = $executorSid
    client_sid = $agentSid
    effective_access_verified = $false
    agent_group_membership_verified = $false
    executor_account = $ExecutorAccount
    agent_account = $AgentAccount
    install_root = $root
    acl = @(
        @{path='code';inheritance=$false;executor='ReadAndExecute';agent='None';administrators='FullControl'},
        @{path='secrets';inheritance=$false;executor='Read';agent='None';administrators='FullControl'},
        @{path='state';inheritance=$false;executor='Modify';agent='None';administrators='FullControl'},
        @{path='evidence';inheritance=$false;executor='Read';agent='Read';administrators='FullControl'}
    )
    ipc = @{
        transport='Windows named pipe'; remote_clients='REJECT';
        allowed_sids=@($executorSid,$agentSid,'S-1-5-32-544');
        max_message_bytes=1048576; request_timeout_seconds=30;
        authenticated_ticket_required=$true; arbitrary_methods=$false;
        operations=@('validate','dry_run'); live_operations_enabled=$false
    }
    activation_blockers=@('UNVERIFIED: run under Agent token and reject Administrators or nested privileged groups','UNVERIFIED: Agent must fail reading API keys, site credentials, HMAC and nonce files','UNVERIFIED: Agent must fail writing code, config and authorization policy','Resolve account SIDs and verify distinct users','Create executor as non-administrator with no interactive logon','Install administrator-owned immutable code','Apply and audit protected ACLs','Provision protected authorization key and credentials','Implement named-pipe ACL and reject remote clients','Validate authenticated framing and replay limits','Run cross-account negative access tests','Obtain separate production activation approval')
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding utf8
Write-Output 'Review manifest generated. No account, ACL, service or network setting changed.'
