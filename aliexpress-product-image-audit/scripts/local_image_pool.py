"""Explicit local official provenance; directory names are not evidence of ownership."""
import json
from pathlib import Path
from urllib.parse import urlparse
from candidate_quality import sha256

def load_official_pool(index):
    index=Path(index).resolve()
    data=json.loads(index.read_text(encoding='utf-8-sig'))
    if data.get('schema')!='official-image-pool/v1' or not isinstance(data.get('items'),list):
        raise ValueError('INVALID_OFFICIAL_POOL_INDEX')
    accepted=[]
    for row in data['items']:
        try:
            if row.get('official_source') is not True or not row.get('model') or row.get('packaging_type') not in {'BOX','FIGURE','MIXED'}:continue
            url=urlparse(row.get('source_url',''))
            if url.scheme not in {'https','http'} or not url.netloc:continue
            path=Path(row['file'])
            if not path.is_absolute():path=index.parent/path
            path=path.resolve()
            if sha256(path)!=row.get('sha256'):continue
            accepted.append(dict(row,file=str(path)))
        except (OSError,KeyError,ValueError,TypeError):continue
    return accepted
