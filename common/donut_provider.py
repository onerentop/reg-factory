# -*- coding: utf-8 -*-
"""
common/donut_provider.py — BrowserProvider 的 donut-browser 实现（走本地 REST API）。

与 common/ixbrowser_provider.py 对齐契约：create→open→close→delete 的窗口语义，
映射到 donut 的 profile 模型：
    create_browser  -> POST /v1/proxies (有代理时) + POST /v1/profiles (wayfern)
    open_browser    -> POST /v1/profiles/{id}/run  → 返回 remote_debugging_port
    close_browser   -> POST /v1/profiles/{id}/kill
    delete_browser  -> DELETE /v1/profiles/{id}
    cleanup_browsers-> 列出 profile，删多余的
    list_browsers   -> GET /v1/profiles

认证：Authorization: Bearer <token>。token 由 scripts/donut_token.py 解密
%LOCALAPPDATA%/DonutBrowserDev/settings/api_token.dat（vault 密码默认）。

注意：run/kill 等 automation 端点要求账号有 browser_automation 权限，否则 402。
用带 e2e feature 重编 + TAURI_AUTOMATION=true + WAYFERN_TEST_TOKEN 的 dev 构建可绕过。

坑：create_profile 带 proxy 时，donut 会对代理做连通性校验（PROXY_NOT_WORKING，
lib.rs:1177）——假/死代理会被 400 拒绝。真代理（如 1024proxy）可正常创建。
"""

import re
import sys
import time
import urllib.request
import urllib.error
import json

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from config import (
    DONUT_API_BASE,
    DONUT_API_TOKEN,
    DONUT_PROFILE_REUSE,
)
from common.browser_provider import BrowserProvider
from common.donut_token import load_token


class DonutAPIError(Exception):
    """donut REST API 调用错误（含 HTTP 状态）。"""

    def __init__(self, status, method, path, body=""):
        self.status = status
        self.method = method
        self.path = path
        self.body = body
        super().__init__(f"donut API {method} {path} -> HTTP {status}: {body[:200]}")


class DonutBrowserProvider(BrowserProvider):
    """走 donut 本地 REST API 的 provider。端口/地址来自 config。"""

    def __init__(self, base=None, token=None, timeout=30):
        self.base = (base or DONUT_API_BASE).rstrip("/")
        self.token = token or DONUT_API_TOKEN or load_token()
        if not self.token:
            raise RuntimeError(
                "未找到 donut API token。请先运行 scripts/donut_token.py 解密并设置 DONUT_API_TOKEN"
            )
        self.timeout = timeout

    # ---------------- 底层 HTTP ----------------
    def _request(self, method, path, body=None, expect_json=True):
        url = f"{self.base}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw:
                    return None
                if expect_json:
                    return json.loads(raw.decode("utf-8"))
                return raw
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise DonutAPIError(e.code, method, path, body)
        except urllib.error.URLError as e:
            raise RuntimeError(f"donut API 网络错误 {method} {path}: {e}")

    def _call(self, method, path, body=None, expect_json=True, timeout=None):
        """带 3 次指数退避重试；profile 创建可传更长的单请求超时。"""
        last = None
        original_timeout = self.timeout
        if timeout is not None:
            self.timeout = timeout
        try:
            for attempt in range(3):
                try:
                    return self._request(method, path, body, expect_json)
                except (DonutAPIError, RuntimeError) as error:
                    last = error
                    # 401/402 不重试（认证/付费墙问题，重试无用）
                    if isinstance(error, DonutAPIError) and error.status in (401, 402):
                        raise
                    time.sleep(2 ** attempt)
            raise last
        finally:
            self.timeout = original_timeout

    # ---------------- 代理解析（与 ixbrowser 同款） ----------------
    @staticmethod
    def _parse_proxy(proxy_str):
        """解析代理串为 donut ProxySettings 结构。支持 socks5/http/https。"""
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
            proxy_type = "https"
            proxy_str = proxy_str[len("https://"):]

        if "@" not in proxy_str and "," in proxy_str:
            proxy_str = proxy_str.replace(",", "@", 1)

        # user:pass@host:port
        match = re.match(r'^(.+):(.+)@(.+):(\d+)$', proxy_str)
        if match:
            return {
                "proxy_type": proxy_type,
                "host": match.group(3),
                "port": int(match.group(4)),
                "username": match.group(1),
                "password": match.group(2),
            }
        # host:port:user:pass (1024proxy 格式，默认 socks5)
        match3 = re.match(r'^([^:]+):(\d+):(.+):([^:]+)$', proxy_str)
        if match3:
            return {
                "proxy_type": proxy_type if proxy_type != "http" else "socks5",
                "host": match3.group(1),
                "port": int(match3.group(2)),
                "username": match3.group(3),
                "password": match3.group(4),
            }
        # host:port
        match2 = re.match(r'^(.+):(\d+)$', proxy_str)
        if match2:
            return {"proxy_type": proxy_type, "host": match2.group(1), "port": int(match2.group(2))}
        return None

    # ---------------- BrowserProvider 接口 ----------------
    def create_browser(self, name="reg", proxy_str=None, **kwargs):
        """创建/复用窗口，确保代理已 upsert 并绑定到 profile。

        代理策略：有同源代理则更新账密，无则新建；然后绑定到当前 profile。
        复用已有 profile 时也会检查代理绑定，缺失则补绑，保证窗口带代理。
        """
        # 1) upsert 代理（有则更新、无则新建），拿到 proxy_id
        proxy_id = None
        parsed = self._parse_proxy(proxy_str)
        if parsed:
            proxy_id = self._create_proxy(name, parsed)

        # 2) 复用已有同名 profile（DONUT_PROFILE_REUSE=true 时）
        if DONUT_PROFILE_REUSE:
            for p in self._fetch_all_profiles():
                if p.get("name") == name:
                    pid = p.get("id")
                    bound_proxy = p.get("proxy_id") or p.get("vpn_id")
                    if proxy_id and not bound_proxy:
                        # 复用 profile 没绑代理 → 补绑
                        print(f"  donut 复用 profile 未绑代理，补绑: {name} (ID: {pid})")
                        self._bind_proxy(pid, proxy_id)
                    elif proxy_id and bound_proxy and bound_proxy != proxy_id:
                        # 复用 profile 绑的代理与当前不一致 → 更新绑定
                        print(
                            f"  donut 复用 profile 代理不一致，更新绑定: "
                            f"{bound_proxy} -> {proxy_id}"
                        )
                        self._bind_proxy(pid, proxy_id)
                    print(f"  donut 复用已有 profile: {name} (ID: {pid})")
                    return pid

        body = {
            "name": name,
            "browser": "wayfern",
        }
        if proxy_id:
            body["proxy_id"] = proxy_id
        if kwargs.get("group_id"):
            body["group_id"] = kwargs["group_id"]

        # Donut 会在关联住宅代理时同步做连通性校验，30 秒不够会留下 proxy
        # 却没有 profile；仅该耗时端点放宽，其他 API 保持默认短超时。
        result = self._call("POST", "/v1/profiles", body, timeout=90)
        pid = result.get("profile", {}).get("id")
        if not pid:
            raise RuntimeError(f"donut create profile 返回无 id: {result}")
        print(f"  donut profile 已创建: {name} (ID: {pid}) 代理绑定: {proxy_id or '无'}")
        return pid

    def _bind_proxy(self, profile_id, proxy_id):
        """PUT /v1/profiles/{id} 绑定代理到 profile。"""
        try:
            result = self._call("PUT", f"/v1/profiles/{profile_id}", {"proxy_id": proxy_id})
            if isinstance(result, dict) and result.get("profile"):
                print(f"  donut profile 代理已绑定: {profile_id} -> {proxy_id}")
            else:
                print(f"  donut profile 代理绑定完成: {profile_id}")
        except Exception as e:
            print(f"  WARN: donut profile 绑代理失败 {profile_id}: {e}")


    def _list_proxies(self):
        """GET /v1/proxies 返回纯 list。"""
        result = self._call("GET", "/v1/proxies")
        return result if isinstance(result, list) else []

    def _create_proxy(self, name, parsed):
        """Upsert 代理配置：同源（host+port+username）已存在则 PUT 更新，
        不存在则 POST 新建，返回 proxy_id。

        Donut 创建带 proxy 的 profile 时会做连通性校验（PROXY_NOT_WORKING，
        lib.rs:1177），假/死代理会被 400 拒绝；而已存在的代理已通过校验，
        更新后直接复用可跳过 30s 校验等待，避免死循环重试。
        """
        proxy_name = f"{name}_proxy"
        settings = {
            "proxy_type": parsed["proxy_type"],
            "host": parsed["host"],
            "port": parsed["port"],
            "username": parsed.get("username"),
            "password": parsed.get("password"),
        }
        # 1) 同名优先（重试/复用场景）
        for p in self._list_proxies():
            if p.get("name") == proxy_name:
                print(f"  donut 更新已有 proxy: {proxy_name} (ID: {p.get('id')})")
                self._update_proxy(p.get("id"), proxy_name, settings)
                return p.get("id")
        # 2) 同源（host+port+username）复用并更新账密
        for p in self._list_proxies():
            ps = p.get("proxy_settings") or {}
            if (
                ps.get("host") == parsed.get("host")
                and ps.get("port") == parsed.get("port")
                and (ps.get("username") or "") == (parsed.get("username") or "")
            ):
                print(
                    f"  donut 更新同源代理: {p.get('name')} (ID: {p.get('id')}) "
                    f"host={ps.get('host')}:{ps.get('port')}"
                )
                self._update_proxy(p.get("id"), p.get("name") or proxy_name, settings)
                return p.get("id")
        # 3) 无则新建
        body = {"name": proxy_name, "proxy_settings": settings}
        result = self._call("POST", "/v1/proxies", body)
        pid = result.get("id")
        if not pid:
            raise RuntimeError(f"donut create proxy 返回无 id: {result}")
        print(f"  donut proxy 已创建: {proxy_name} (ID: {pid})")
        return pid

    def _update_proxy(self, proxy_id, name, settings):
        """PUT /v1/proxies/{id} 更新代理配置（同步最新账密）。"""
        body = {"name": name, "proxy_settings": settings}
        try:
            result = self._call("PUT", f"/v1/proxies/{proxy_id}", body)
            if isinstance(result, dict) and result.get("id"):
                print(f"  donut proxy 已更新: {name} (ID: {proxy_id})")
            else:
                print(f"  donut proxy 更新完成: {proxy_id}")
        except Exception as e:
            print(f"  WARN: donut proxy 更新失败 {proxy_id}: {e}")


    def open_browser(self, profile_id):
        # run 带 headless 参数（默认有头），返回 remote_debugging_port
        result = self._call("POST", f"/v1/profiles/{profile_id}/run", {"headless": False, "url": None})
        port = result.get("remote_debugging_port")
        if not port:
            raise RuntimeError(f"donut run 返回无 remote_debugging_port: {result}")
        ws = f"http://127.0.0.1:{port}"
        print(f"  donut profile 已打开: {profile_id} (CDP http://127.0.0.1:{port})")
        return {"ws": ws, "http": ws}

    def close_browser(self, profile_id):
        try:
            self._call("POST", f"/v1/profiles/{profile_id}/kill", expect_json=False)
        except Exception as e:
            print(f"  关闭 profile 失败 {profile_id}: {e}")

    def delete_browser(self, profile_id):
        try:
            self._call("DELETE", f"/v1/profiles/{profile_id}", expect_json=False)
            print(f"  profile 已删除: {profile_id}")
        except Exception as e:
            print(f"  删除 profile 失败 {profile_id}: {e}")

    def _fetch_all_profiles(self):
        result = self._call("GET", "/v1/profiles")
        return result.get("profiles", []) if isinstance(result, dict) else []

    def list_browsers(self, page=0, page_size=100):
        profiles = self._fetch_all_profiles()
        rows = [
            {
                "id": p.get("id"),
                "name": p.get("name", ""),
                "remark": "",
                "seq": p.get("id", 0),
            }
            for p in profiles
        ]
        return {"data": {"list": rows}}

    def cleanup_browsers(self, keep=0):
        profiles = self._fetch_all_profiles()
        if not profiles:
            print("  无 profile 需要清理")
            return 0
        # 按 last_launch 排序，新的在前，删掉 keep 之后的多余 profile
        profiles.sort(key=lambda p: p.get("last_launch") or 0, reverse=True)
        to_delete = profiles[keep:]
        deleted = 0
        for p in to_delete:
            pid = p.get("id")
            self.close_browser(pid)
            time.sleep(1)
            try:
                self._call("DELETE", f"/v1/profiles/{pid}", expect_json=False)
                deleted += 1
            except Exception as e:
                print(f"  删除失败 {p.get('name', '')}: {e}")
        print(f"  清理完成: 删除 {deleted}/{len(to_delete)} 个 profile")
        return deleted

    def select_browser(self):
        profiles = self._fetch_all_profiles()
        print("\n可用的 donut profile:")
        print("-" * 50)
        if profiles:
            for i, p in enumerate(profiles):
                print(f"  [{i}] #{p.get('id')} {p.get('name', '未命名')}  running={p.get('is_running')}")
        else:
            print("  (无)")
        print("  [n] 创建新 profile")
        print("-" * 50)
        while True:
            max_idx = len(profiles) - 1 if profiles else -1
            hint = f"[0-{max_idx}/n]" if profiles else "[n]"
            choice = input(f"请选择 {hint}: ").strip().lower()
            if choice == "n":
                name = input("profile 名称 (留空自动): ").strip() or f"reg_{len(profiles) + 1}"
                return self.create_browser(name=name)
            if profiles and choice.isdigit() and 0 <= int(choice) < len(profiles):
                selected = profiles[int(choice)]
                print(f"已选择: {selected.get('name', '')} (ID: {selected.get('id')})")
                return selected.get("id")
            print("无效选择，请重新输入。")
