"""Process-owned account locks; kernel release handles crashes, across job roots."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import time

DEFAULT_DIRECTORY=Path(__file__).resolve().parents[1]/'local'/'execution_locks'

@contextmanager
def account_lock(account,directory=None,timeout=30):
    directory=Path(directory or DEFAULT_DIRECTORY);directory.mkdir(parents=True,exist_ok=True)
    path=directory/(hashlib.sha256(str(account).encode()).hexdigest()+'.lock')
    # Never unlink a lock file: a queued handle must continue to refer to the same inode.
    with path.open('a+b') as stream:
        deadline=time.monotonic()+timeout
        while True:
            try:
                stream.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except (OSError,BlockingIOError):
                if time.monotonic()>=deadline:raise TimeoutError('ACCOUNT_LOCK_TIMEOUT')
                time.sleep(.05)
        try:
            # Windows can lock a byte beyond EOF. Initialize only while owning that byte.
            stream.seek(0,os.SEEK_END)
            if stream.tell()==0:stream.write(b'0');stream.flush()
            yield
        finally:
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)

def account_key(writer,root):
    if callable(getattr(type(writer),'account_fingerprint',None)):
        return writer.account_fingerprint()
    explicit=getattr(writer,'coordination_key',None)
    if isinstance(explicit,str) and explicit:return explicit
    return 'local-root:'+str(Path(root).resolve())
