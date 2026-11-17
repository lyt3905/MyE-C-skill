import tempfile,unittest
from pathlib import Path
from mye_c_automation.upload_rate import UploadRateLimiter
class UploadRateTests(unittest.TestCase):
 def test_independent_instances_share_spacing_and_failure_keeps_limit(self):
  with tempfile.TemporaryDirectory() as root:
   now=[100.0];waits=[]
   def sleep(seconds):waits.append(seconds);now[0]+=seconds
   def limiter():return UploadRateLimiter(Path(root)/'global.sqlite',interval=.5,clock=lambda:now[0],sleep=sleep)
   with limiter().slot():pass
   with self.assertRaises(RuntimeError):
    with limiter().slot():raise RuntimeError('fake upload failure')
   with limiter().slot():pass
   self.assertEqual(waits,[.5,.5])
 def test_invalid_interval_is_rejected(self):
  with self.assertRaises(ValueError):UploadRateLimiter('unused',interval=0)
 def test_two_processes_share_global_upload_channel(self):
  import subprocess,sys,os,json
  with tempfile.TemporaryDirectory() as root:
   code='import sys,time,json;from mye_c_automation.upload_rate import UploadRateLimiter;from pathlib import Path\nwith UploadRateLimiter(sys.argv[1],interval=.1).slot():\n start=time.time();time.sleep(.03);Path(sys.argv[2]).write_text(json.dumps([start,time.time()]))'
   processes=[subprocess.Popen([sys.executable,'-c',code,str(Path(root)/'rate.sqlite'),str(Path(root)/(str(i)+'.json'))],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE) for i in range(2)]
   for process in processes:
    _,error=process.communicate(timeout=10);self.assertEqual(process.returncode,0,error.decode(errors='replace'))
   windows=sorted(json.loads((Path(root)/(str(i)+'.json')).read_text()) for i in range(2))
   self.assertGreaterEqual(windows[1][0]-windows[0][1],.08)
