"""Cross-process, cross-account upload pacing; unrelated to per-job budgets."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import time

class UploadRateLimiter:
    def __init__(self,path=None,*,interval=.5,clock=time.time,sleep=time.sleep):
        if interval<=0:raise ValueError('positive upload interval required')
        self.path=Path(path) if path is not None else __import__('mye_c_automation.paths',fromlist=['data_root']).data_root()/'ledger'/'global_upload_rate.sqlite'
        self.interval=interval;self.clock=clock;self.sleep=sleep

    @contextmanager
    def slot(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        connection=sqlite3.connect(self.path,timeout=60)
        try:
            connection.execute('CREATE TABLE IF NOT EXISTS pacing (id INTEGER PRIMARY KEY, next_at REAL NOT NULL)')
            connection.commit()
            connection.execute('BEGIN IMMEDIATE')
            row=connection.execute('SELECT next_at FROM pacing WHERE id=1').fetchone()
            while row and row[0]>self.clock():
                self.sleep(min(.5,row[0]-self.clock()))
            # Keep the global lease until upload returns, including failures.
            try:yield
            finally:
                connection.execute('INSERT OR REPLACE INTO pacing VALUES (1,?)',(self.clock()+self.interval,))
                connection.commit()
        finally:connection.close()
