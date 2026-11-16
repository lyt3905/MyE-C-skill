"""Install independently owned local weight bytes; never download or infer."""
import hashlib
import os
import shutil
import uuid
from pathlib import Path

def file_sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def install_lama(source,destination,expected_sha256):
    source=Path(source).expanduser().resolve();destination=Path(destination).expanduser().absolute()
    if (not isinstance(expected_sha256,str) or len(expected_sha256)!=64 or
        any(c not in '0123456789abcdef' for c in expected_sha256)):
        raise ValueError('INVALID_MODEL_CHECKSUM')
    if not source.is_file():raise ValueError('MODEL_SOURCE_MISSING')
    if file_sha256(source)!=expected_sha256:raise ValueError('MODEL_CHECKSUM_MISMATCH')
    if destination.exists() or destination.is_symlink():
        if destination.is_symlink() or not destination.is_file() or file_sha256(destination)!=expected_sha256:
            raise ValueError('MODEL_DESTINATION_EXISTS')
        return dict(status='ALREADY_INSTALLED',path=str(destination.resolve()),sha256=expected_sha256,bytes=destination.stat().st_size,inference='NOT_RUN')
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.installing')
    try:
        with source.open('rb') as original,temporary.open('xb') as copy:
            shutil.copyfileobj(original,copy,1024*1024);copy.flush();os.fsync(copy.fileno())
        if file_sha256(temporary)!=expected_sha256:raise ValueError('MODEL_CHECKSUM_MISMATCH')
        # The temporary is a new local copy, not a link to the source. Linking it
        # into place commits complete bytes atomically and refuses an existing name.
        try:os.link(temporary,destination)
        except FileExistsError as exc:raise ValueError('MODEL_DESTINATION_EXISTS') from exc
    finally:
        temporary.unlink(missing_ok=True)
    return dict(status='INSTALLED',path=str(destination.resolve()),sha256=expected_sha256,bytes=destination.stat().st_size,inference='NOT_RUN')
