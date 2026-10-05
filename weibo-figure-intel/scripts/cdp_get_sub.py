#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 Edge/Chrome 的 CDP 远程调试端口自动提取微博 SUB。

原理：不解密浏览器 cookie 库（App-Bound Encryption 已封死这条路），
而是启动一个带 --remote-debugging-port 的浏览器实例，用 CDP 的
Network.getAllCookies 命令让浏览器**自己**吐出 HttpOnly 的 SUB。

为什么能用：Network.getAllCookies 是浏览器内核级 API，返回的是解密后的
明文 cookie，不受 HttpOnly 限制（HttpOnly 只挡 JS 的 document.cookie）。

依赖：仅标准库（手写 WebSocket 客户端）。

用法：
    python cdp_get_sub.py probe            # 探测当前是否有调试端口可用
    python cdp_get_sub.py grab             # 连接现有调试端口，抓 SUB 并校验
    python cdp_get_sub.py grab --port 9222
    python cdp_get_sub.py grab --write     # 抓取并写回 wb_cookie.json
"""

import argparse
import base64
import json
import os
import secrets
import socket
import struct
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(HERE, "wb_cookie.json")

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


# ---------------------------------------------------------------- WebSocket

class WsError(Exception):
    pass


class MiniWebSocket:
    """极简 WebSocket 客户端（仅文本帧，够 CDP 用）。"""

    def __init__(self, url, timeout=30, default_port=None):
        # url 形如 ws://127.0.0.1:9222/devtools/page/XXXX
        if not url.startswith("ws://"):
            raise WsError("仅支持 ws://")
        rest = url[5:]
        hostport, _, path = rest.partition("/")
        path = "/" + path
        host, _, port = hostport.partition(":")
        # ⚠️ 实测坑：部分 Edge 版本的 webSocketDebuggerUrl **不含端口号**
        # （形如 ws://127.0.0.1/devtools/page/XXX），此时绝不能 fallback 到 80
        # ——那会 ConnectionRefused 并被误判成「实例挂了」。用已知的调试端口补上。
        if not port:
            if not default_port:
                raise WsError(f"wsUrl 无端口且未提供 default_port: {url}")
            port = str(default_port)
        # ⚠️ 同样要绕过代理：socket.create_connection 会读 HTTP_PROXY，
        # 把本机回环地址也代理出去，表现为 ConnectionRefused（极易误判为「端口没开」）。
        # 这里直接自建裸 socket，不走 create_connection。
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect((host, int(port)))
        self.sock.settimeout(timeout)
        self._handshake(host, port, path)

    def _handshake(self, host, port, path):
        key = base64.b64encode(secrets.token_bytes(16)).decode()
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise WsError("握手时连接被关闭")
            buf += chunk
        head = buf.split(b"\r\n\r\n", 1)[0].decode("latin-1")
        if "101" not in head.split("\r\n")[0]:
            raise WsError(f"握手失败: {head.splitlines()[0]}")
        self._buf = buf.split(b"\r\n\r\n", 1)[1]

    # -- 帧收发 --

    def send(self, text):
        payload = text.encode("utf-8")
        header = bytearray([0x81])  # FIN + text
        n = len(payload)
        mask = secrets.token_bytes(4)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _read_exact(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise WsError("连接被关闭")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def recv(self):
        while True:
            b0, b1 = self._read_exact(2)
            opcode = b0 & 0x0F
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read_exact(8))[0]
            data = self._read_exact(length)
            if opcode == 0x9:  # ping -> pong
                self.sock.sendall(bytes([0x8A, 0x80]) + secrets.token_bytes(4))
                continue
            if opcode == 0x8:  # close
                raise WsError("对端关闭连接")
            if opcode in (0x1, 0x2, 0x0):
                return data.decode("utf-8", "replace")

    def call(self, method, params=None, timeout=30, _id=None):
        mid = _id or int(time.time() * 1000) % 1000000
        self.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(self.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise WsError(f"{method} 报错: {msg['error']}")
                return msg.get("result", {})
        raise WsError(f"{method} 超时")

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------- CDP HTTP

def http_json(url, timeout=5):
    # ⚠️ 必须绕过系统代理：本机开了代理（如 Clash）时，127.0.0.1 会被代理
    # 转发上去而拿到 502 Bad Gateway，看起来像「端口没开」，极易误判。
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={"Host": "127.0.0.1"})
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def probe(port):
    """探测调试端口是否可用，返回 (ok, info)。"""
    try:
        ver = http_json(f"http://127.0.0.1:{port}/json/version", timeout=3)
        return True, ver
    except Exception as e:
        return False, str(e)


def find_target(port):
    """找一个可用的 CDP target（优先 page 类型）。"""
    tabs = http_json(f"http://127.0.0.1:{port}/json/list", timeout=5)
    pages = [t for t in tabs if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if pages:
        return pages[0]
    anyw = [t for t in tabs if t.get("webSocketDebuggerUrl")]
    if anyw:
        return anyw[0]
    raise WsError("没有可用的调试 target")


# ---------------------------------------------------------------- 抓 SUB

def grab_sub(port, verify=True, retries=3):
    # ⚠️ 必须「每次重试都重新取 target」：CDP 的 webSocketDebuggerUrl 是短时效的，
    # 页面导航/回收后旧 URL 会立刻 ConnectionRefused，看起来像端口挂了。
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            target = find_target(port)
            print(f"[CDP] 连接 target: {target.get('title', '?')[:60]}")
            ws = MiniWebSocket(target["webSocketDebuggerUrl"], timeout=30, default_port=port)
            try:
                res = ws.call("Network.getAllCookies", timeout=30)
            finally:
                ws.close()
            break
        except (WsError, OSError, ConnectionRefusedError) as e:
            last_err = e
            print(f"[CDP] 第 {attempt} 次尝试失败：{e}")
            if attempt < retries:
                time.sleep(1.5)
    else:
        return None, f"连接 CDP 失败（重试 {retries} 次）：{last_err}"
    return _pick_sub(res, verify)


def _pick_sub(res, verify=True):
    cookies = res.get("cookies", [])
    print(f"[CDP] 浏览器共返回 {len(cookies)} 条 cookie")

    subs = [c for c in cookies if c.get("name") == "SUB"]
    if not subs:
        return None, "浏览器 cookie 里没有 SUB —— 该浏览器实例未登录微博"

    # 按 domain 分组展示（不打印值）
    print("[CDP] 找到的 SUB 及所属域：")
    for c in subs:
        print(f"       domain={c.get('domain'):<16} httponly={c.get('httpOnly')} "
              f"expires={c.get('expires', -1)} len={len(c.get('value',''))}")

    # 优先取 .weibo.com（桌面端接口只认这个域，见 SKILL.md 已知限制 1）
    chosen = None
    for c in subs:
        if c.get("domain") == ".weibo.com":
            chosen = c
            break
    if chosen is None:
        for c in subs:
            if "weibo.com" in (c.get("domain") or ""):
                chosen = c
                break
    if chosen is None:
        chosen = subs[0]

    print(f"[CDP] 选用 domain={chosen['domain']}")
    value = chosen.get("value", "")
    if not value:
        return None, "选中的 SUB 值为空"

    if verify:
        ok, msg = verify_sub(value)
        print(f"[CDP] 登录校验: {'✅ ' + msg if ok else '❌ ' + msg}")
        if not ok:
            return None, f"抓到的 SUB 未通过校验：{msg}（可能该浏览器实例的登录态已失效，需重新登录微博）"

    return value, "ok"


def verify_sub(sub_value):
    """用 friendships/friends 校验 SUB 是否有效。"""
    cookie = sub_value if sub_value.startswith("SUB=") else f"SUB={sub_value}"
    req = urllib.request.Request(
        "https://weibo.com/ajax/friendships/friends?page=1",
        headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
            "Referer": "https://weibo.com/",
            "X-Requested-With": "XMLHttpRequest",
            "Cookie": cookie,
        },
    )
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=25) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return False, f"请求异常 {e}"

    if data.get("ok") == 1:
        users = data.get("users") or []
        total = data.get("total_number")
        return True, f"账号={users[0].get('screen_name') if users else '?'} 关注={total} 人"
    return False, f"ok={data.get('ok')}"


def write_cookie(sub_value):
    """写回 wb_cookie.json，保留其他字段。"""
    cookie = sub_value if sub_value.startswith("SUB=") else f"SUB={sub_value}"
    old = {}
    if os.path.exists(COOKIE_FILE):
        try:
            old = json.load(open(COOKIE_FILE, encoding="utf-8"))
        except Exception:
            old = {}
    old["cookie"] = cookie
    old["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(old, f, ensure_ascii=False, indent=2)
    print(f"[CDP] 已写回 {COOKIE_FILE}（SUB 前缀 {cookie[:12]}… 长度 {len(cookie)}）")


def main():
    ap = argparse.ArgumentParser(description="通过 CDP 自动提取微博 SUB")
    ap.add_argument("action", choices=["probe", "grab"])
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--write", action="store_true", help="抓取成功后写回 wb_cookie.json")
    ap.add_argument("--no-verify", action="store_true", help="跳过登录校验")
    args = ap.parse_args()

    ok, info = probe(args.port)
    if not ok:
        print(f"❌ 端口 {args.port} 上没有调试接口：{info}")
        print()
        print("⚠️ 必须先完全退出 Edge，且**必须用独立 user-data-dir**——")
        print("   Chrome/Edge 136+ 禁止在默认 profile 上启用远程调试（端口会静默不开）。")
        print("   首次开出来后在其中手动登录一次微博，之后即可长期自动续期：")
        print(f'  "{EDGE_PATHS[0]}" --user-data-dir="C:\\Users\\<你>\\EdgeWeibo" --remote-debugging-port={args.port}')
        return 2

    print(f"✅ 调试端口可用：{info.get('Browser', info)}")
    if args.action == "probe":
        return 0

    val, msg = grab_sub(args.port, verify=not args.no_verify)
    if not val:
        print(f"❌ {msg}")
        return 1

    print(f"✅ 成功获取 SUB（前缀 {val[:12]}… 长度 {len(val)}）")
    if args.write:
        write_cookie(val)
    else:
        print("（未写回文件；加 --write 才会写回 wb_cookie.json）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
