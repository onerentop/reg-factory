# -*- coding: utf-8 -*-
"""
common/ant_provider.py — BrowserProvider 的 Ant Browser 实现（走本地 REST API 19876）。

与 common/ixbrowser_provider.py / donut_provider.py 对齐窗口语义:
    create_browser  -> POST /api/profiles {"profile":{...}}     创建 profile
    open_browser    -> POST /api/launch {profileId}             启动→返回 debugPort
    close_browser   -> POST /api/runtime/stop {profileId}       停止活跃实例
    delete_browser  -> POST stop + DELETE /api/profiles/{id}    先停再删(运行中删 409)
    list_browsers   -> GET /api/profiles
    cleanup_browsers-> 列出 + 删多余

契约已对运行中的 Ant API 实测校准(见 spec 第 8 节):
- 创建请求体嵌套 {"profile":{...}},响应顶层 profileId
- launch 同步返回 debugPort/debugReady,无需轮询
- stop 需 {profileId} selector(空 body 400);delete 须先 stop
- CDP 端点 http://127.0.0.1:{debugPort}(真实 Chrome 端点)

认证:仅当 ANT_API_KEY 非空时附加 X-Ant-Api-Key 头。
"""

import sys
import time
import json
import urllib.request
import urllib.error

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from config import ANT_API_BASE, ANT_API_KEY
from common.browser_provider import BrowserProvider


class AntAPIError(Exception):
    """Ant REST API 调用错误(含 HTTP 状态)。"""

    def __init__(self, status, method, path, body=""):
        self.status = status
        self.method = method
        self.path = path
        self.body = body
        super().__init__(f"Ant API {method} {path} -> HTTP {status}: {str(body)[:200]}")


class AntBrowserProvider(BrowserProvider):
    """走 Ant Browser 本地 REST API 的 provider。地址/密钥来自 config。"""

    def __init__(self, base=None, api_key=None, timeout=30, retries=3):
        self.base = (base or ANT_API_BASE).rstrip("/")
        self.api_key = api_key if api_key is not None else ANT_API_KEY
        self.timeout = timeout
        self.retries = retries

    # ---------------- HTTP ----------------
    def _request(self, method, path, body=None):
        url = self.base + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("X-Ant-Api-Key", self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                err_body = ""
            raise AntAPIError(e.code, method, path, err_body)
        except urllib.error.URLError as e:
            raise AntAPIError(0, method, path, f"URLError: {e}")

    def _call(self, method, path, body=None):
        """调用 REST。网络抖动(status==0)与 5xx 服务端错误指数退避重试;
        4xx 业务错误(参数/状态)立即抛。"""
        last = None
        for attempt in range(self.retries + 1):
            try:
                return self._request(method, path, body)
            except AntAPIError as e:
                last = e
                # status==0 网络层 / status>=500 服务端瞬时错误 -> 重试
                # 400<=status<500 确定性业务错误 -> 立即抛
                transient = e.status == 0 or e.status >= 500
                if transient and attempt < self.retries:
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise last

    # ---------------- BrowserProvider 接口 ----------------
    def create_browser(self, name="reg", proxy_str=None, **kwargs):
        proxy_config = proxy_str.strip() if proxy_str and proxy_str.strip() else "direct://"
        body = {"profile": {
            "profileName": name,
            "proxyConfig": proxy_config,
            "coreId": kwargs.get("core_id", ""),
        }}
        result = self._call("POST", "/api/profiles", body)
        pid = result.get("profileId")
        if not pid:
            raise RuntimeError(f"Ant create profile 返回无 profileId: {result}")
        return pid

    # 以下 6 个方法在 Task 3/4 逐个用 TDD 替换。
    # 此处先给非抽象占位,使 AntBrowserProvider 可实例化(BrowserProvider 是 ABC,
    # 7 个抽象方法必须全部有具体实现才能实例化)。
    def open_browser(self, profile_id):
        r = self._call("POST", "/api/launch", {"profileId": profile_id})
        debug_port = r.get("debugPort")
        if r.get("debugReady") and debug_port:
            ep = f"http://127.0.0.1:{debug_port}"
            return {"ws": ep, "http": ep}
        # 兜底:短轮询 runtime/active(实测通常 launch 即就绪,此为极端兜底)
        for _ in range(15):
            rt = self._call("GET", "/api/runtime/active")
            if rt.get("profileId") == profile_id and rt.get("debugReady") and rt.get("debugPort"):
                ep = f"http://127.0.0.1:{rt['debugPort']}"
                return {"ws": ep, "http": ep}
            time.sleep(1)
        raise AntAPIError(0, "GET", "/api/runtime/active", "debug not ready")

    def close_browser(self, profile_id):
        try:
            self._call("POST", "/api/runtime/stop", {"profileId": profile_id})
        except Exception:
            pass

    def delete_browser(self, profile_id):
        # delete 对运行中实例返回 409,必须先 stop
        try:
            self._call("POST", "/api/runtime/stop", {"profileId": profile_id})
        except Exception:
            pass
        try:
            self._call("DELETE", f"/api/profiles/{profile_id}", None)
        except Exception:
            pass

    def _fetch_all_profiles(self):
        return self._call("GET", "/api/profiles").get("items", [])

    def list_browsers(self, page=0, page_size=100):
        rows = [{
            "id": p.get("profileId"),
            "name": p.get("profileName", ""),
            "remark": p.get("userDataDir", ""),
            "seq": p.get("profileId", ""),
        } for p in self._fetch_all_profiles()]
        return {"data": {"list": rows}}

    def cleanup_browsers(self, keep=0):
        rows = self._fetch_all_profiles()
        to_delete = rows[keep:]
        for p in to_delete:
            self.delete_browser(p.get("profileId"))
        return len(to_delete)

    def select_browser(self):
        rows = self._fetch_all_profiles()
        print("\n可用的浏览器实例:")
        print("-" * 50)
        if rows:
            for i, p in enumerate(rows):
                print(f"  [{i}] {p.get('profileId')}  {p.get('profileName', '未命名')}")
        else:
            print("  (无)")
        print("  [n] 创建新实例")
        print("-" * 50)
        while True:
            max_idx = len(rows) - 1 if rows else -1
            hint = f"[0-{max_idx}/n]" if rows else "[n]"
            choice = input(f"请选择 {hint}: ").strip().lower()
            if choice == "n":
                name = input("实例名称 (留空自动): ").strip() or f"reg_{len(rows) + 1}"
                return self.create_browser(name=name)
            if rows and choice.isdigit() and 0 <= int(choice) < len(rows):
                return rows[int(choice)].get("profileId")
            print("无效选择,请重新输入。")
