"""Bounded JSON over local Windows named pipes; never uses pickle.
Production host must run under an isolated account with protected config/code/state.
"""
import argparse
import ctypes
from ctypes import wintypes as W
import json
import re
import threading
import queue
from pathlib import Path
from multiprocessing.connection import PipeConnection, Client
from mye_c_automation.executor.authorization import Authorization
from mye_c_automation.executor.service import ExecutorService

MAX_FRAME = 65536
TIMEOUT = 5

def encode(value):
    data = json.dumps(value,allow_nan=False,separators=(',',':')).encode('utf-8')
    if len(data)>MAX_FRAME: raise ValueError('frame too large')
    return data

def decode(data):
    if len(data)>MAX_FRAME: raise ValueError('frame too large')
    try: return json.loads(data,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite')))
    except (UnicodeError,json.JSONDecodeError) as exc: raise ValueError('invalid JSON') from exc

def receive(conn, timeout=TIMEOUT):
    # Closing a synchronous pipe does not cancel an in-flight read: cancel the
    # reader thread's Windows I/O before closing it on timeout.
    result = queue.Queue(maxsize=1)
    def read():
        try: result.put((True, conn.recv_bytes(MAX_FRAME)))
        except Exception as exc: result.put((False, exc))
    worker = threading.Thread(target=read, daemon=True)
    worker.start()
    try: ok, value = result.get(timeout=timeout)
    except queue.Empty:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenThread.restype = W.HANDLE
        handle = kernel.OpenThread(0x0001, False, worker.native_id)
        if handle:
            kernel.CancelSynchronousIo.argtypes = [W.HANDLE]
            kernel.CloseHandle.argtypes = [W.HANDLE]
            kernel.CancelSynchronousIo(handle)
            kernel.CloseHandle(handle)
        worker.join(timeout=1)
        raise TimeoutError('executor frame timeout')
    if not ok: raise value
    return value


def server_sid(conn):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    adv = ctypes.WinDLL('advapi32', use_last_error=True)
    pid = W.ULONG()
    kernel.GetNamedPipeServerProcessId.argtypes = [W.HANDLE, ctypes.POINTER(W.ULONG)]
    if not kernel.GetNamedPipeServerProcessId(conn.fileno(), ctypes.byref(pid)):
        raise ctypes.WinError(ctypes.get_last_error())
    kernel.OpenProcess.restype = W.HANDLE
    process = kernel.OpenProcess(0x1000, False, pid.value)
    token = W.HANDLE()
    kernel.CloseHandle.argtypes = [W.HANDLE]
    adv.OpenProcessToken.argtypes = [W.HANDLE,W.DWORD,ctypes.POINTER(W.HANDLE)]
    try:
        if not process or not adv.OpenProcessToken(process, 8, ctypes.byref(token)):
            raise ctypes.WinError(ctypes.get_last_error())
        size = W.DWORD()
        adv.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        if not adv.GetTokenInformation(token, 1, buf, size, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        sid = ctypes.cast(buf,ctypes.POINTER(ctypes.c_void_p))[0]
        value = W.LPWSTR()
        adv.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p,ctypes.POINTER(W.LPWSTR)]
        if not adv.ConvertSidToStringSidW(sid,ctypes.byref(value)):
            raise ctypes.WinError(ctypes.get_last_error())
        try: return value.value
        finally:
            kernel.LocalFree.argtypes=[ctypes.c_void_p]
            kernel.LocalFree(value)
    finally:
        if token: kernel.CloseHandle(token)
        if process: kernel.CloseHandle(process)


def request(address, body, expected_server_sid=None):
    if expected_server_sid is None:
        raise ValueError('expected server SID required')
    data = encode(body)
    with Client(address,family='AF_PIPE') as conn:
        if server_sid(conn) != expected_server_sid:
            raise PermissionError('executor server identity mismatch')
        conn.send_bytes(data)
        return decode(receive(conn))

def listen(address,sid):
    if not re.fullmatch(r'S-1-5-(?:\d+-)*\d+',sid): raise ValueError('explicit client SID required')
    if not address.startswith('\\\\.\\pipe\\ae-audit-'): raise ValueError('invalid pipe name')
    adv=ctypes.WinDLL('advapi32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ctypes.c_void_p]
    kernel.LocalFree.restype=ctypes.c_void_p
    kernel.CloseHandle.argtypes=[W.HANDLE]
    descriptor=ctypes.c_void_p()
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes=[W.LPCWSTR,W.DWORD,ctypes.POINTER(ctypes.c_void_p),ctypes.c_void_p]
    if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(f'D:P(A;;GA;;;SY)(A;;GA;;;OW)(A;;GRGW;;;{sid})',1,ctypes.byref(descriptor),None): raise ctypes.WinError(ctypes.get_last_error())
    class SA(ctypes.Structure):
        _fields_=[('length',W.DWORD),('descriptor',ctypes.c_void_p),('inherit',W.BOOL)]
    security=SA(ctypes.sizeof(SA),descriptor,False)
    kernel.CreateNamedPipeW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,W.DWORD,W.DWORD,W.DWORD,W.DWORD,ctypes.POINTER(SA)]
    kernel.CreateNamedPipeW.restype=W.HANDLE
    kernel.ConnectNamedPipe.argtypes=[W.HANDLE,ctypes.c_void_p]
    try:
        handle=kernel.CreateNamedPipeW(address,0x00000003|0x00080000,0x0000000e,1,MAX_FRAME,MAX_FRAME,5000,ctypes.byref(security))
        if handle==ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    finally: kernel.LocalFree(descriptor)
    if not kernel.ConnectNamedPipe(handle,None) and ctypes.get_last_error()!=535:
        kernel.CloseHandle(W.HANDLE(handle)); raise ctypes.WinError(ctypes.get_last_error())
    return PipeConnection(handle)

class FakeWriter:
    def __init__(self,state,log): self.state=state; self.log=Path(log)
    def product(self,pid): return self.state
    def save(self,pid,product,**kwargs):
        self.state=product
        with self.log.open('a',encoding='utf-8') as stream: stream.write('save\n')

def serve(config):
    secret=Path(config['secret_file']).read_bytes()
    auth=Authorization(secret,config['nonce_database'])
    if config.get('fake',False): writer=FakeWriter(config.get('state',{}),config['write_log'])
    else:
        # Deliberately no environment or cwd credential discovery.
        from mye_c_automation.executor.deployment_preflight import preflight
        report = preflight(config, config.get('_config_path'))
        if not report['ok']: raise ValueError('deployment blocked: ' + repr(report['blockers']))
        from mye_c_automation.site_client import _SiteTransport as Site
        from mye_c_automation.executor.site_write_client import SiteWriteClient
        import inspect
        if 'cfg' not in inspect.signature(Site).parameters: raise ValueError('explicit credential adapter required')
        writer=SiteWriteClient(Site(cfg=json.loads(Path(config['credentials_file']).read_text(encoding='utf-8')), verify_tls=True))
    service=ExecutorService(auth,writer,config['evidence_root'])
    for _ in range(config.get('max_requests',100)):
        with listen(config['address'],config['client_sid']) as conn:
            try:
                body=decode(receive(conn))
                if type(body) is not dict or set(body)-{'plan','ticket','dry_run'}: raise ValueError('invalid request')
                dry=body.get('dry_run',True)
                if type(dry) is not bool: raise ValueError('dry_run must be boolean')
                if dry is not True and config.get('enable_writes') is not True: raise ValueError('writes disabled')
                if hasattr(writer, 'metrics'):
                    writer.metrics = dict.fromkeys(writer.metrics, 0)
                from mye_c_automation.budget_manager import BudgetManager
                limits=json.loads((Path(__file__).parents[1]/'config'/'budget.v2.json').read_text(encoding='utf-8'))['limits']
                budget=BudgetManager(limits,service.root/('executor-'+body['plan']['job_id']+'.sqlite'))
                try:
                    service.budget=budget
                    result=service.execute(body['plan'],body.get('ticket'),dry)
                finally:
                    budget.close()
                    service.budget=None
                from mye_c_automation.plan_v2 import plan_hash
                result.update(job_id=body['plan']['job_id'],plan_sha256=plan_hash(body['plan']))
                response={'ok':True,'result':result}
            except Exception:
                response={'ok':False,'error':'request rejected'}
            try: conn.send_bytes(encode(response))
            except (OSError, EOFError): pass

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('mode',choices=['serve','request']); parser.add_argument('file'); parser.add_argument('--address'); parser.add_argument('--server-sid')
    args=parser.parse_args(); data=json.loads(Path(args.file).read_text(encoding='utf-8'))
    if args.mode=='serve':
        data['_config_path'] = str(Path(args.file).resolve())
        serve(data)
    else: print(json.dumps(request(args.address,data,args.server_sid)))
if __name__=='__main__': main()
