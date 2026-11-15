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
