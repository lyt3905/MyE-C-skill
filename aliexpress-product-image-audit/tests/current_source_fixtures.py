"""Freeze the current source for NEW synthetic acceptance Jobs only.

Historical test manifests and all 433 raw evidence files remain unchanged.
The real production entry still rejects its outdated historical baseline.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import run_8788_real_validation as rv


def freeze_current_source(case):
    tmp=tempfile.TemporaryDirectory();case.addCleanup(tmp.cleanup)
    path=Path(tmp.name)/'fake-tested-source.json'
    source=rv.source_versions()['files']
    path.write_text(json.dumps({'run_id':'FAKE_CURRENT_SOURCE_FIXTURE',
        'source_after':{name:{'sha256':digest} for name,digest in source.items()}}))
    guard=patch.object(rv,'BASELINE',path);guard.start();case.addCleanup(guard.stop)
    # Archived runner tests exercise their original dual-model Fake contract;
    # the current production gateway profile is DeepSeek-only.
    profile=Path(tmp.name)/'legacy-fake-model-profile.json'
    config=json.loads(rv.DEFAULT_CONFIG.read_text(encoding='utf-8'))
    config['models']=['deepseek-v4.1-flash','mimo-v2.6-pro']
    profile.write_text(json.dumps(config),encoding='utf-8')
    profile_guard=patch.object(rv,'DEFAULT_CONFIG',profile)
    profile_guard.start();case.addCleanup(profile_guard.stop)
    # observed_audit captured the old default path at import time.
    import observed_audit as oa
    defaults_guard=patch.object(oa.prepare,'__kwdefaults__',dict(oa.prepare.__kwdefaults__,config_path=profile))
    defaults_guard.start();case.addCleanup(defaults_guard.stop)
