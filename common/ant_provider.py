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

_RETRYABLE = [
    "connection refused", "connection reset", "econnrefused", "econnreset",
    "timed out", "timeout", "network", "socket", "urlopen error",
]


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

    @staticmethod
    def _is_retryable(msg):
        m = str(msg).lower()
        return any(k in m for k in _RETRYABLE)

    def _call(self, method, path, body=None):
        """调用 REST。网络抖动指数退避重试;HTTP >=400(AntAPIError)业务错误直接抛。"""
        last = None
        for attempt in range(self.retries + 1):
            try:
                return self._request(method, path, body)
            except AntAPIError as e:
                last = e
                # HTTP 层错误(有 status)是业务错误,不重试;status==0 是网络层
                if e.status == 0 and attempt < self.retries and self._is_retryable(e.body):
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
        return result["profileId"]

    # 以下 6 个方法在 Task 3/4 逐个用 TDD 替换。
    # 此处先给非抽象占位,使 AntBrowserProvider 可实例化(BrowserProvider 是 ABC,
    # 7 个抽象方法必须全部有具体实现才能实例化)。
    def open_browser(self, profile_id):
        raise NotImplementedError

    def close_browser(self, profile_id):
        raise NotImplementedError

    def delete_browser(self, profile_id):
        raise NotImplementedError

    def cleanup_browsers(self, keep=0):
        raise NotImplementedError

    def list_browsers(self, page=0, page_size=100):
        raise NotImplementedError

    def select_browser(self):
        raise NotImplementedError
