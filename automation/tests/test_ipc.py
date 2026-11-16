import unittest
from mye_c_automation.executor.ipc import encode, decode
class IPCCodecTests(unittest.TestCase):
    def test_limits_and_json(self):
        self.assertEqual(decode(encode({'dry_run':True})), {'dry_run':True})
        with self.assertRaises(ValueError): encode({'x':'x'*70000})
        with self.assertRaises(ValueError): decode(b'not json')

class IPCProcessTests(unittest.TestCase):
    def test_real_process_authorization(self):
        import subprocess, sys, tempfile, time, uuid, json
        from pathlib import Path
        from mye_c_automation.executor.ipc import request
        from mye_c_automation.executor.authorization import sign
        from mye_c_automation.plan_v2 import plan_hash
        from mye_c_automation.product_state import canonical_state_hash
        sid=subprocess.check_output(['whoami','/user','/fo','csv','/nh'],text=True).strip().split(',')[-1].strip('"')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); secret=b'x'*32; (root/'secret').write_bytes(secret)
            address='\\\\.\\pipe\\ae-audit-'+uuid.uuid4().hex
            cfg=dict(address=address,client_sid=sid,secret_file=str(root/'secret'),nonce_database=str(root/'nonce.db'),evidence_root=tmp,fake=True,state={'id':1,'shopId':7,'images':{'main':['https://x/a'],'detail':['https://x/b']}},enable_writes=True,write_log=str(root/'writes'),max_requests=10)
            (root/'config.json').write_text(json.dumps(cfg))
            proc=subprocess.Popen([sys.executable,'-m','mye_c_automation.executor.ipc','serve',str(root/'config.json')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            plan=dict(schema='token-opt-plan/v2',job_id='JOB_test',pid=1,shop=7,workflow_version='token-opt-v2',policy_version='v2',precondition={'state_sha256':canonical_state_hash(cfg['state'])},evidence_refs=[],ai_judgement_refs=[],desired={},post_actions=[],review={'status':'RESOLVED'})
            ticket=sign(dict(job_id='JOB_test',pid=1,shop=7,plan_sha256=plan_hash(plan),expires_at=time.time()+60,allowed_operations=['site_save'],max_site_saves=1,nonce='n'*32),secret)
            def call(body):
                for i in range(100):
                    try: return request(address,body,sid)
                    except FileNotFoundError: time.sleep(.02)
                raise AssertionError('server unavailable: '+str(proc.poll()))
            try:
                # A spoofed identity must fail before any request bytes are sent.
                for _ in range(100):
                    try:
                        with self.assertRaises(PermissionError):
                            request(address, {}, 'S-1-5-18' if sid != 'S-1-5-18' else 'S-1-5-19')
                        break
                    except FileNotFoundError: time.sleep(.02)
                # Malformed JSON and a disconnected peer cannot kill the host.
                from multiprocessing.connection import Client
                for payload in (b'not json', b'{}'):
                    for _ in range(100):
                        try:
                            with Client(address, family='AF_PIPE') as peer:
                                peer.send_bytes(payload)
                            break
                        except FileNotFoundError: time.sleep(.02)
                # Real Windows handle stays connected without completing a frame.
                # The host must time out and accept a subsequent connection.
                from mye_c_automation.executor.ipc import TIMEOUT
                for _ in range(100):
                    try:
                        stalled = Client(address, family='AF_PIPE')
                        break
                    except FileNotFoundError: time.sleep(.02)
                started = time.monotonic()
                try:
                    self.assertTrue(stalled.poll(TIMEOUT + 3))
                    self.assertFalse(decode(stalled.recv_bytes())['ok'])
                    self.assertLess(time.monotonic() - started, TIMEOUT + 3)
                finally: stalled.close()
                # Oversized native pipe message bypasses the application encoder.
                for _ in range(100):
                    try:
                        with Client(address, family='AF_PIPE') as malicious:
                            try:
                                malicious.send_bytes(b'x' * 70000)
                                self.assertTrue(malicious.poll(3))
                                self.assertFalse(decode(malicious.recv_bytes())['ok'])
                            except BrokenPipeError:
                                pass  # Host rejected the oversized message before write completed.
                        break
                    except FileNotFoundError: time.sleep(.02)
                self.assertFalse(call(dict(plan=plan,dry_run=False))['ok'])
                changed=dict(plan,shop=8)
                self.assertFalse(call(dict(plan=changed,ticket=ticket,dry_run=False))['ok'])
                self.assertTrue(call(dict(plan=plan,dry_run=True))['ok'])
                self.assertFalse((root/'writes').exists())
                self.assertTrue(call(dict(plan=plan,ticket=ticket,dry_run=False))['ok'])
                self.assertFalse(call(dict(plan=plan,ticket=ticket,dry_run=False))['ok'])
                proc.wait(timeout=10)
                self.assertFalse((root/'writes').exists())  # No-op still consumes the authorization nonce.
                self.assertEqual(proc.returncode,0,proc.stderr.read().decode())
            finally:
                if proc.poll() is None: proc.kill(); proc.wait()
                proc.stdout.close(); proc.stderr.close()

class IPCIdentityTests(unittest.TestCase):
    def test_identity_required_before_connect(self):
        from mye_c_automation.executor.ipc import request, listen
        with self.assertRaises(ValueError): request('unused', {})
        with self.assertRaises(ValueError): listen('unused', 'Everyone')

    def test_receive_timeout_cancels_partial_read(self):
        from mye_c_automation.executor.ipc import receive
        import time
        class Slow:
            def recv_bytes(self, limit):
                time.sleep(.1)
                return b'{}'
        with self.assertRaises(TimeoutError): receive(Slow(), .01)
