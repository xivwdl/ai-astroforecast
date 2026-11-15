import json
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


class RestrictedRedirect(HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != "https" or target.netloc not in self.hosts:
            raise OSError("Unexpected upstream redirect")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def request_bytes(url, *, payload=None, token=None, limit=2_000_000, timeout=15, redirect_hosts=None):
    headers = {"User-Agent": "AI-Astroforecast/1.0", "Accept": "*/*"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=data, headers=headers)
    open_request = urlopen
    if redirect_hosts is not None or token:
        open_request = build_opener(RestrictedRedirect(redirect_hosts or set())).open
    with open_request(request, timeout=timeout) as response:
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError("Upstream response is too large")
    return body


def get_json(url, **kwargs):
    return json.loads(request_bytes(url, **kwargs))
