"""Writable data paths never depend on the caller's working directory."""
import os
from pathlib import Path

def data_root(override=None):
    value=override or os.environ.get('MYEC_DATA_ROOT')
    if value:return Path(value).expanduser().resolve()
    project=Path(__file__).resolve().parents[2]
    if (project/'pyproject.toml').is_file():return project/'data'
    base=Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))
    return base/'mye-c-automation/data'

def initialize_data(override=None):
    root=data_root(override)
    for folder in ('jobs','cache','ledger','logs','snapshots','reports'):
        (root/folder).mkdir(parents=True,exist_ok=True)
    return root

def config_root(override=None):
    value=override or os.environ.get('MYEC_CONFIG_DIR')
    if value:return Path(value).expanduser().resolve()
    project=Path(__file__).resolve().parents[2]
    if (project/'pyproject.toml').is_file():return project/'local'
    return Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'mye-c-automation/config'
