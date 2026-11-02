#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""极简 CDP 客户端：用本机 Edge（独立 user-data-dir）在后台打开页面并取渲染后的文本。
供 link_probe.py 复用；也可单独当命令行工具：
    python cdp_util.py "https://item.taobao.com/item.htm?id=123" --profile C:\\Users\\shana\\EdgeWeibo
"""
import json, os, socket, subprocess, sys, time, urllib.parse, urllib.request

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(EDGE):
    EDGE = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"


def port_open(port=9222, host="127.0.0.1"):
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def http_json(path, port=9222, method="GET"):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read().decode("utf-8", "ignore")
    return json.loads(body) if body.strip().startswith(("{", "[")) else body


def ensure_browser(profile, port=9222, headless=False, timeout=25):
    """确保带调试端口的 Edge 在跑；已在跑则直接复用（返回 False 表示复用了已有实例）。"""
    if port_open(port):
        return False
    args = [EDGE, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
            "--no-first-run", "--no-default-browser-check", "about:blank"]
    if headless:
        args.insert(1, "--headless=new")
    subprocess.Popen(args, close_fds=True)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if port_open(port):
            time.sleep(1.0)
            return True
        time.sleep(0.4)
    raise RuntimeError(f"Edge 调试端口 {port} 未起来（profile={profile}）")


class Tab:
    def __init__(self, ws_url, target_id, port=9222):
        import websocket
        self.id = target_id
        self.port = port
        self.ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
        self._n = 0

    def send(self, method, params=None, timeout=30):
        self._n += 1
        msg_id = self._n
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        t0 = time.time()
        while time.time() - t0 < timeout:
            data = json.loads(self.ws.recv())
            if data.get("id") == msg_id:
                if "error" in data:
                    raise RuntimeError(f"{method} -> {data['error']}")
                return data.get("result", {})
        raise TimeoutError(method)

    def goto(self, url, wait_ms=2500, ready_timeout=20):
        self.send("Page.enable")
        self.send("Page.navigate", {"url": url})
        t0 = time.time()
        while time.time() - t0 < ready_timeout:
            try:
                st = self.send("Runtime.evaluate", {"expression": "document.readyState",
                                                    "returnByValue": True})["result"].get("value")
                if st == "complete":
                    break
            except Exception:
                pass
            time.sleep(0.4)
        time.sleep(wait_ms / 1000.0)
        return self.url()

    def url(self):
        return self.send("Runtime.evaluate", {"expression": "location.href",
                                              "returnByValue": True})["result"].get("value")

    def eval(self, expression):
        r = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True,
                                           "awaitPromise": True})
        return r["result"].get("value")

    def text(self, expression="document.body ? document.body.innerText : ''"):
        return self.eval(expression) or ""

    def title(self):
        return self.eval("document.title") or ""

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        try:
            http_json(f"/json/close/{self.id}", self.port)
        except Exception:
            pass


def open_tab(url="about:blank", port=9222, profile=None, headless=False):
    if profile:
        ensure_browser(profile, port=port, headless=headless)
    elif not port_open(port):
        raise RuntimeError(f"调试端口 {port} 未开启")
    quoted = urllib.parse.quote(url, safe=":/?=&%#")
    try:
        info = http_json(f"/json/new?{quoted}", port, method="PUT")
    except Exception:
        info = http_json(f"/json/new?{quoted}", port)
    return Tab(info["webSocketDebuggerUrl"], info["id"], port)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--profile", default=r"C:\Users\shana\EdgeWeibo")
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--wait", type=int, default=3000)
    ap.add_argument("--js", default=None, help="自定义取文本表达式")
    ap.add_argument("--keep", action="store_true", help="不关闭标签页，方便人工查看")
    a = ap.parse_args()
    tab = open_tab(a.url, port=a.port, profile=a.profile)
    try:
        final = tab.goto(a.url, wait_ms=a.wait)
        print("TITLE:", tab.title())
        print("URL:", final)
        txt = tab.text(a.js) if a.js else tab.text()
        print("--- TEXT ---")
        print(txt[:4000])
    finally:
        if not a.keep:
            tab.close()


if __name__ == "__main__":
    main()
