"""Privileged-process Site adapter; instantiate only after authorization checks."""
class SiteWriteClient:
    def __init__(self, site):
        self.site = site
        import hashlib,json
        cfg=getattr(site,'cfg',{})
        if not isinstance(cfg,dict):cfg={}
        self.coordination_key=hashlib.sha256(json.dumps({k:cfg.get(k) for k in ('base','user')},sort_keys=True).encode()).hexdigest()
        self.metrics = dict(site_get_calls=0,site_save_calls=0,upload_calls=0,translate_calls=0,status_calls=0)
    def product(self,pid):
        self.metrics['site_get_calls'] += 1
        return self.site.product(pid)
    def current_shop(self):
        probe=getattr(self.site,'current_shop',None)
        if not callable(probe):raise ValueError('SHOP_CONTEXT_UNVERIFIED: transport current_shop missing')
        return probe()
    def account_fingerprint(self):
        probe=getattr(self.site,'account_fingerprint',None)
        if not callable(probe):raise ValueError('ACCOUNT_PRINCIPAL_UNVERIFIED')
        return probe()
    def readonly_client(self):
        from site_client import ReadOnlySiteClient
        return ReadOnlySiteClient.from_transport(self.site)
    def save(self,pid,product,*,expected_state_sha256):
        if self.metrics['site_save_calls'] >= 1:
            raise ValueError('save limit exceeded')
        self.metrics['site_save_calls'] += 1
        # Site.save performs one final GET and state hash check internally.
        self.metrics['site_get_calls'] += 1
        extra={k:product[k] for k in ('titleEn','titleTranslationZh','skus','price','weight','identityJson','brandId') if k in product}
        return self.site.save(pid,images=product.get('images'),desc=product.get('descriptionJson'),extra=extra,expected_state_hash=expected_state_sha256)
    def upload(self,path):
        self.metrics['upload_calls'] += 1
        return self.site.upload(path)
    def fetch_image(self,url):
        import urllib.request
        from urllib.parse import urlparse
        if urlparse(url).scheme not in {'https','http'}: raise ValueError('invalid saved image URL')
        request=urllib.request.Request(url,headers={
            'User-Agent':'Mozilla/5.0',
            'Accept':'image/jpeg,image/png,image/webp,image/*;q=0.8',
            'Referer':'https://www.aliexpress.com/'})
        with urllib.request.urlopen(request,timeout=60) as response:
            data=response.read(20*1024*1024+1)
        if len(data)>20*1024*1024: raise ValueError('saved image too large')
        return data
    def translate(self,pid,title):
        if self.metrics['translate_calls'] >= 2:
            raise ValueError('translation limit exceeded')
        self.metrics['translate_calls'] += 1
        return self.site.call(f'/api/admin/products/{pid}/translate-title',{'titleEn':title},method='POST')
