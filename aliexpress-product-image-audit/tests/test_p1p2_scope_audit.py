import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from audit_one import audit
class ScopeAuditV12Tests(unittest.TestCase):
 def test_SCOPE_01_02_no_description_network_or_analysis(self):
  from copy import deepcopy
  product={'id':1,'images':{'main':['https://x/m'+str(i) for i in range(3)],'detail':['https://x/d'+str(i) for i in range(3)],'sku':['https://x/s0','https://x/s1'],'ai':['https://x/ai'],'scene':['https://x/scene']},'skus':[],'descriptionJson':{'blocks':[{'type':'image','url':'https://forbidden/404-'+str(i)+'.jpg','text':'竞争店名中文海报'} for i in range(10)]}}
  for description in (product['descriptionJson'],'not json invalid {'):
   with self.subTest(description_type=type(description).__name__),tempfile.TemporaryDirectory() as root:
    current=deepcopy(product);current['descriptionJson']=description;seen=[]
    class Site:
     def current_shop(self):return 7
     def product(self,pid):return deepcopy(current)
    def download(url,path):
     self.assertTrue(url.startswith('https://x/'));self.assertNotIn(url,['https://x/ai','https://x/scene']);seen.append(url);Image.new('RGB',(800,800),'blue').save(path,format='PNG')
    class OCR:
     def __call__(self,image):return ([],None)
    with patch('audit_one.description_checks',side_effect=AssertionError('opaque field')),patch('audit_one._head_status',side_effect=AssertionError('no HEAD')):
     audit(1,7,output_dir=Path(root),site=Site(),downloader=download,ocr_factory=OCR)
    raw=json.loads((Path(root)/'audit_raw.json').read_text(encoding='utf-8'));flags=json.loads((Path(root)/'audit_flags.json').read_text(encoding='utf-8'))
    self.assertEqual(len(raw['images']),8);self.assertEqual(len(set(seen)),8)
    self.assertFalse(any('description' in str(row).lower() for row in flags.get('anomalies',[])))
