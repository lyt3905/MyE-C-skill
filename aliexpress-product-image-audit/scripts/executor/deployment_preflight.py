"""Read-only Windows deployment inspection. Never changes ACLs or creates files."""
import json
import os
from pathlib import Path
import subprocess

# Includes directory delete-child, write-DACL and write-owner rights.
READ_MASK = 0x80000000 | 0x10000000 | 0x00020089
WRITE_MASK = 0x40000000 | 0x10000000 | 0x000D0156

def inspect_windows(path):
    script = r'''$ErrorActionPreference='Stop'; $p=$env:AE_PREFLIGHT_PATH
$i=[Security.Principal.WindowsIdentity]::GetCurrent()
$a=if ([IO.Directory]::Exists($p)) {[IO.Directory]::GetAccessControl($p)} else {[IO.File]::GetAccessControl($p)}
[pscustomobject]@{sid=$i.User.Value;owner=$a.GetOwner([Security.Principal.SecurityIdentifier]).Value;protected=$a.AreAccessRulesProtected;rules=@($a.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]) | ForEach-Object {[pscustomobject]@{sid=$_.IdentityReference.Value;allow=($_.AccessControlType -eq 'Allow');rights=[long]$_.FileSystemRights}});reparse=(([IO.File]::GetAttributes($p) -band [IO.FileAttributes]::ReparsePoint) -ne 0)} | ConvertTo-Json -Depth 5 -Compress'''
    env = dict(os.environ, AE_PREFLIGHT_PATH=str(path))
    env.pop('PSModulePath', None)
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],env=env,capture_output=True,text=True,timeout=15,check=True)
    return json.loads(result.stdout)

def preflight(config, config_path=None, inspector=inspect_windows):
    blockers, checks = [], []
    server, client = config.get('server_sid'), config.get('client_sid')
    if not server or not client or server == client:
        blockers.append('distinct explicit server_sid and client_sid required')
    # ACL inspection cannot prove the Agent token's nested group memberships.
    # Require a separately performed cross-account probe; never infer isolation.
    blockers.append('UNVERIFIED: cross-account Agent token administrator membership and effective access probes required')
    targets = [('code',Path(__file__).resolve().parents[1]),('interpreter',Path(os.sys.executable))]
    for label, value in [('config',config_path),('key',config.get('secret_file')),('credentials',config.get('credentials_file')),('nonce',config.get('nonce_database')),('evidence',config.get('evidence_root'))]:
        if not value or not Path(value).is_absolute():
            blockers.append(label+': absolute existing path required'); continue
        targets.append((label,Path(value)))
    trusted={server,'S-1-5-18','S-1-5-32-544'}
    seen=set()
    for label, target in targets:
        # Inspect every ancestor too: writable parent permits replacing a protected child.
        paths=[target,*target.parents]
        if target.is_dir(): paths += list(target.rglob('*'))
        for path in paths:
            key=str(path).casefold()
            if key in seen: continue
            seen.add(key)
            try:
                if not path.exists(): raise ValueError('path must exist before deployment')
                info=inspector(path)
                if info['sid'] != server: blockers.append(f'{label}: current process SID differs from server_sid')
                if info.get('reparse'): blockers.append(f'{path}: reparse point prohibited')
                if info['owner'] not in trusted: blockers.append(f'{path}: untrusted owner')
                rules=info.get('rules') or []
                if isinstance(rules,dict): rules=[rules]
                if not rules: blockers.append(f'{path}: empty or null DACL cannot be accepted')
                if label in {'key','credentials','nonce'} and path == target:
                    for rule in rules:
                        if rule['allow'] and int(rule['rights']) & READ_MASK and rule['sid'] not in trusted:
                            blockers.append(f'{path}: secret-readable ACE for {rule["sid"]}')
                    if info.get('protected') is not True:
                        blockers.append(f'{path}: secret ACL inheritance must be disabled')
                for rule in rules:
                    if rule['allow'] and int(rule['rights']) & WRITE_MASK and rule['sid'] not in trusted:
                        blockers.append(f'{path}: write-capable ACE for {rule["sid"]}')
                checks.append({'path':str(path),'owner':info['owner'],'current_sid':info['sid'],'dacl_inspected':True})
            except Exception as exc:
                blockers.append(f'{path}: inspection failed ({type(exc).__name__})')
    return {'ok':not blockers,'blockers':list(dict.fromkeys(blockers)),'checks':checks}

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('config');a=p.parse_args()
    path=Path(a.config).resolve()
    report=preflight(json.loads(path.read_text(encoding='utf-8')),path)
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(0 if report['ok'] else 2)

if __name__=='__main__': main()
