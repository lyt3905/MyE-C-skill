"""Standalone copies of the existing project HTTP and JSON helpers (stdlib only)."""
import json
import re
import urllib.request

class _NoModelRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('MODEL_REDIRECT_FORBIDDEN')


def _open_model_request(request,timeout):
    from model_config import require_enabled_model
    require_enabled_model(json.loads(request.data)["model"])
    # No proxy discovery or redirects can silently change the approved route.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoModelRedirect())
    return opener.open(request,timeout=timeout)

def parse_json_content(content):
    """Accept JSON or one complete JSON code fence, without extracting prose."""
    if not isinstance(content, str):
        raise TypeError('response content must be text')
    content = content.strip()
    fence = re.fullmatch(r'```(?:json)?[ \t]*\r?\n(.*?)\r?\n```', content, re.DOTALL)
    if fence:
        content = fence.group(1)
    return json.loads(content)

