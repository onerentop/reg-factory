# -*- coding: utf-8 -*-
"""
common/ixbrowser_provider.py — BrowserProvider 的 ixBrowser 实现。

基于官方 ixbrowser-local-api（IXBrowserClient）。client 方法成功返回
dict/True，失败返回 None（错误信息在 client.message / client.code）。
本类用 _call 统一包装：网络抖动指数退避重试，业务错误抛异常。
"""

import re
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from ixbrowser_local_api import IXBrowserClient
from ixbrowser_local_api.entities import Profile, Proxy, Fingerprint

from config import IXBROWSER_TARGET, IXBROWSER_PORT
from common.browser_provider import BrowserProvider

_RETRYABLE = [
    "socket disconnected", "tls connection", "connection refused",
    "connection reset", "network", "timeout", "econnrefused",
    "econnreset", "etimedout", "certificate",
]


class IXBrowserProvider(BrowserProvider):
    def __init__(self, target=None, port=None, retries=3):
        self.target = target or IXBROWSER_TARGET
        self.port = int(port or IXBROWSER_PORT)
        self.retries = retries
        self._client = None

    # ---------------- client / 重试 ----------------
    def _get_client(self):
        if self._client is None:
            self._client = IXBrowserClient(target=self.target, port=self.port)
        return self._client

    def _reset_client(self):
        self._client = None

    @staticmethod
    def _is_retryable(msg):
        if not msg:
            return False
        m = str(msg).lower()
        return any(k in m for k in _RETRYABLE)

    def _call(self, method_name, *args, **kwargs):
        """调用 client.<method_name>(*args, **kwargs)，None 视为失败。
        网络类错误指数退避重试；业务错误（client.message）抛 Exception。"""
        last = None
        for attempt in range(self.retries + 1):
            try:
                client = self._get_client()
                result = getattr(client, method_name)(*args, **kwargs)
                if result is None:
                    msg = getattr(client, "message", None) or "unknown error"
                    last = msg
                    if attempt < self.retries and self._is_retryable(msg):
                        self._reset_client()
                        time.sleep(2 ** attempt)
                        continue
                    raise Exception(f"ixBrowser {method_name} 失败: {msg}")
                return result
            except Exception as e:
                last = str(e)
                if attempt < self.retries and self._is_retryable(last):
                    self._reset_client()
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise Exception(f"ixBrowser {method_name} 重试后仍失败: {last}")

    # ---------------- 代理解析（从 register_outlook_standalone 迁移） ----------------
    @staticmethod
    def _parse_proxy(proxy_str):
        """解析代理串。支持：
          socks5://user:pass@host:port / socks5://host:port
          user:pass@host:port / host:port （默认 http）
        返回 dict 或 None。"""
        if not proxy_str:
            return None
        proxy_type = "http"
        lower = proxy_str.lower()
        if lower.startswith("socks5://"):
            proxy_type = "socks5"
            proxy_str = proxy_str[len("socks5://"):]
        elif lower.startswith("http://"):
            proxy_str = proxy_str[len("http://"):]
        elif lower.startswith("https://"):
            proxy_str = proxy_str[len("https://"):]

        if "@" not in proxy_str and "," in proxy_str:
            proxy_str = proxy_str.replace(",", "@", 1)

        match = re.match(r'^(.+):(.+)@(.+):(\d+)$', proxy_str)
        if match:
            return {
                "type": proxy_type,
                "username": match.group(1),
                "password": match.group(2),
                "host": match.group(3),
                "port": match.group(4),
            }
        match2 = re.match(r'^(.+):(\d+)$', proxy_str)
        if match2:
            return {"type": proxy_type, "host": match2.group(1), "port": match2.group(2)}
        return None

    # ---------------- 指纹（对齐旧 coreVersion=130） ----------------
    @staticmethod
    def _build_fingerprint():
        fp = Fingerprint()
        fp.ua_type = 1            # PC
        fp.platform = "Windows"
        fp.kernel_version = "130"
        fp.hardware_concurrency = 8   # 与 STEALTH_JS 伪造值一致
        fp.device_memory = 8
        return fp

    # ---------------- BrowserProvider 接口 ----------------
    def create_browser(self, name="reg", proxy_str=None, **kwargs):
        profile = Profile()
        profile.name = name
        profile.note = kwargs.get("remark", "reg-factory")
        if kwargs.get("group_id"):
            profile.group_id = kwargs["group_id"]
        profile.fingerprint_config = self._build_fingerprint()

        proxy = Proxy()
        parsed = self._parse_proxy(proxy_str)
        if parsed:
            proxy.change_to_custom_mode(
                proxy_type=parsed["type"],
                proxy_ip=parsed["host"],
                proxy_port=str(parsed["port"]),
                proxy_user=parsed.get("username"),
                proxy_password=parsed.get("password"),
            )
        else:
            proxy.change_to_custom_mode(proxy_type="direct")
        profile.proxy_config = proxy

        result = self._call("create_profile", profile)
        pid = result.get("profile_id") if isinstance(result, dict) else result
        print(f"  ixBrowser 窗口已创建: {name} (ID: {pid})")
        return pid

    def open_browser(self, profile_id):
        result = self._call(
            "open_profile", int(profile_id),
            cookies_backup=False, load_profile_info_page=False,
        )
        ws = (result.get("ws") or "").strip() if isinstance(result, dict) else ""
        http = (result.get("debugging_address") or "").strip() if isinstance(result, dict) else ""
        if not ws and http:
            # ixBrowser 只给 debug 地址时，用 http endpoint 让 Playwright 自动发现 ws
            ws = http if http.startswith("http") else f"http://{http}"
        return {"ws": ws, "http": http}

    def close_browser(self, profile_id):
        try:
            self._call("close_profile", int(profile_id))
        except Exception:
            pass

    def delete_browser(self, profile_id):
        try:
            self._call("delete_profile", int(profile_id))
            print(f"  窗口已删除: {profile_id}")
        except Exception:
            pass

    def _fetch_all_profiles(self):
        all_rows, page = [], 1
        while True:
            data = self._call("get_profile_list", page=page, limit=100, group_id=0)
            data = data or []
            all_rows.extend(data)
            if len(data) < 100:
                break
            page += 1
        return all_rows

    def list_browsers(self, page=0, page_size=100):
        # ixBrowser 分页从 1 开始；旧接口 page=0 表示首页
        ix_page = page + 1 if page == 0 else page
        data = self._call("get_profile_list", page=ix_page, limit=page_size, group_id=0) or []
        rows = [
            {
                "id": p.get("profile_id"),
                "name": p.get("name", ""),
                "remark": p.get("note", ""),
                "seq": p.get("profile_id", 0),
            }
            for p in data
        ]
        return {"data": {"list": rows}}

    def cleanup_browsers(self, keep=0):
        rows = self._fetch_all_profiles()
        if not rows:
            print("  无窗口需要清理")
            return 0
        rows.sort(key=lambda b: b.get("profile_id", 0), reverse=True)  # 最新在前
        to_delete = rows[keep:]
        deleted = 0
        for b in to_delete:
            pid = b.get("profile_id")
            self.close_browser(pid)
            time.sleep(1)
            try:
                self._call("delete_profile", int(pid))
                deleted += 1
            except Exception as e:
                print(f"  删除失败 {b.get('name', '')}: {e}")
        print(f"  清理完成: 删除 {deleted}/{len(to_delete)} 个窗口")
        return deleted

    def select_browser(self):
        rows = self._fetch_all_profiles()
        print("\n可用的浏览器窗口:")
        print("-" * 50)
        if rows:
            for i, b in enumerate(rows):
                print(f"  [{i}] #{b.get('profile_id')} {b.get('name', '未命名')}  {b.get('note', '')}")
        else:
            print("  (无)")
        print("  [n] 创建新窗口")
        print("-" * 50)
        while True:
            max_idx = len(rows) - 1 if rows else -1
            hint = f"[0-{max_idx}/n]" if rows else "[n]"
            choice = input(f"请选择 {hint}: ").strip().lower()
            if choice == "n":
                name = input("窗口名称 (留空自动): ").strip() or f"reg_{len(rows) + 1}"
                return self.create_browser(name=name)
            if rows and choice.isdigit() and 0 <= int(choice) < len(rows):
                selected = rows[int(choice)]
                print(f"已选择: {selected.get('name', '')} (ID: {selected.get('profile_id')})")
                return selected.get("profile_id")
            print("无效选择，请重新输入。")
