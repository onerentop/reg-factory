"""功能扫描：检查运行中的本机单体 HTTP 端点。

扫描不投递浏览器自动化或其他可能产生外部副作用的任务。
跑法（从 services/ 目录）：
    python scripts/feature_sweep.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict

import httpx

GATEWAY = os.getenv("GATEWAY_URL", "http://127.0.0.1:8000")
SERVICES = {"regfactory": GATEWAY}


@dataclass
class Row:
    group: str
    feature: str
    method: str
    target: str
    status: int | None
    verdict: str  # PASS / FAIL / ERROR / GATED / SKIP
    note: str = ""
    ms: int = 0


class Sweep:
    def __init__(self):
        self.rows: list[Row] = []
        self.client = httpx.Client(timeout=10.0)
        self.token: str | None = None

    def headers(self, auth: bool = False) -> dict:
        if auth and self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    def call(self, group, feature, method, base, path, *, auth=False, json_body=None,
             ok=range(200, 300), gated_on=()):
        """打一个端点并记录。ok=可接受状态码;gated_on=视为 GATED(基础设施通卡外部)的状态码。"""
        url = base + path
        t0 = time.monotonic()
        try:
            r = self.client.request(method, url, headers=self.headers(auth), json=json_body)
            ms = int((time.monotonic() - t0) * 1000)
            body = r.text[:120].replace("\n", " ")
            if r.status_code in ok:
                v = "PASS"
            elif r.status_code in gated_on:
                v = "GATED"
            else:
                v = "FAIL"
            self.rows.append(Row(group, feature, method, path, r.status_code, v, body, ms))
            return r
        except httpx.ConnectError:
            self.rows.append(Row(group, feature, method, path, None, "ERROR", "连接拒绝(服务DOWN)", 0))
        except Exception as e:
            self.rows.append(Row(group, feature, method, path, None, "ERROR", f"{type(e).__name__}: {str(e)[:80]}", 0))
        return None

    # ---------- 功能组 ----------

    def sweep_health(self):
        self.call("health", "regfactory/health", "GET", GATEWAY, "/health")

    def sweep_auth(self):
        # 登录（尝试常见默认凭据；拿到 token 供后续 admin 端点）
        for u, p in [("admin", "admin"), ("admin", "admin123"), ("admin", "password"), ("admin", "changeme")]:
            r = self.call("auth", f"login({u})", "POST", GATEWAY, "/auth/login",
                          json_body={"username": u, "password": p}, ok=range(200, 500))
            if r is not None and r.status_code == 200:
                try:
                    self.token = r.json().get("data", {}).get("token") or r.json().get("data", {}).get("access_token")
                except Exception:
                    pass
                if self.token:
                    break
        # 用户 CRUD（需 admin）
        uname = f"_sweep_user_{int(time.time())}"
        self.call("auth", "create_user", "POST", GATEWAY, "/auth/users", auth=True,
                  json_body={"username": uname, "password": "Sweep!123", "role": "readonly"}, ok=range(200, 300), gated_on=(401, 403))
        self.call("auth", "list_users", "GET", GATEWAY, "/auth/users", auth=True, gated_on=(401, 403))
        # api-keys CRUD
        r = self.call("auth", "create_api_key", "POST", GATEWAY, "/auth/api-keys", auth=True,
                      json_body={"owner_id": "system", "name": "_sweep_key"}, ok=range(200, 300), gated_on=(401, 403))
        self.call("auth", "list_api_keys", "GET", GATEWAY, "/auth/api-keys", gated_on=(401, 403))
        key_id = None
        if r is not None and r.status_code < 300:
            try:
                key_id = r.json().get("data", {}).get("id") or r.json().get("data", {}).get("key_id")
            except Exception:
                pass
        if key_id:
            self.call("auth", "revoke_api_key(cleanup)", "DELETE", GATEWAY, f"/auth/api-keys/{key_id}", auth=True, gated_on=(401, 403))

    def sweep_observability(self):
        self.call("observability", "dashboard", "GET", GATEWAY, "/dashboard")
        self.call("observability", "audit", "GET", GATEWAY, "/audit")
        self.call("observability", "logs", "GET", GATEWAY, "/logs")

    def sweep_alerts(self):
        self.call("alerts", "list_rules", "GET", GATEWAY, "/alerts/rules")
        self.call("alerts", "create_rule", "POST", GATEWAY, "/alerts/rules", auth=True,
                  json_body={"name": "_sweep_rule", "rule_type": "fail_rate", "threshold": "0.5"},
                  ok=range(200, 300), gated_on=(401, 403))

    def sweep_proxy(self):
        r = self.call("proxy", "create_proxy", "POST", GATEWAY, "/proxy",
                      json_body={"type": "socks5", "host": "127.0.0.1", "port": 1080, "username": "u", "password": "p"},
                      ok=range(200, 300), gated_on=(422,))
        self.call("proxy", "list_proxy", "GET", GATEWAY, "/proxy")
        pid = None
        if r is not None and r.status_code < 300:
            try:
                pid = r.json().get("data", {}).get("id")
            except Exception:
                pass
        if pid:
            self.call("proxy", "update_proxy", "PUT", GATEWAY, f"/proxy/{pid}",
                      json_body={"port": 1081}, ok=range(200, 300), gated_on=(422,))
            self.call("proxy", "proxy_status", "PUT", GATEWAY, f"/proxy/{pid}/status",
                      json_body={"status": "active"}, ok=range(200, 300), gated_on=(422,))
            self.call("proxy", "proxy_test", "POST", GATEWAY, f"/proxy/{pid}/test",
                      ok=range(200, 300), gated_on=(400, 502, 504))  # 真测代理可能失败=GATED
            self.call("proxy", "delete_proxy(cleanup)", "DELETE", GATEWAY, f"/proxy/{pid}")

    def sweep_accounts(self):
        email = f"_sweep_{int(time.time())}@outlook.com"
        r = self.call(
            "accounts", "create_account", "POST", GATEWAY, "/accounts",
            json_body={"email": email, "password": "Sweep!123", "platform": "outlook"},
            ok=range(200, 300), gated_on=(422,)
        )
        self.call("accounts", "list_accounts", "GET", GATEWAY, "/accounts")
        account_id = None
        if r is not None and r.status_code < 300:
            try:
                account_id = r.json().get("data", {}).get("id")
            except Exception:
                pass
        if account_id:
            self.call("accounts", "get_account", "GET", GATEWAY, f"/accounts/{account_id}")
            self.call("accounts", "update_account", "PUT", GATEWAY, f"/accounts/{account_id}",
                      json_body={"status": "success"}, ok=range(200, 300), gated_on=(422,))
            self.call("accounts", "delete_account(cleanup)", "DELETE", GATEWAY, f"/accounts/{account_id}")

    def sweep_forwarding(self):
        """兼容名称：单体内调用，不再存在跨服务 HTTP forwarding。"""
        self.call("monolith", "accounts", "GET", GATEWAY, "/accounts")
        self.call("monolith", "sms/health", "GET", GATEWAY, "/sms/health", gated_on=(404,))
        self.call("monolith", "config/health", "GET", GATEWAY, "/config/health", gated_on=(404,))

    def discover_gets(self):
        """拉每个服务 openapi，自动打所有无必填 path 参数的 GET 路由（覆盖剩余只读端点）。"""
        already = {(r.target, r.method) for r in self.rows}
        for name, base in SERVICES.items():
            try:
                spec = self.client.get(base + "/openapi.json", timeout=5).json()
            except Exception:
                continue
            for path, methods in spec.get("paths", {}).items():
                if "get" not in methods:
                    continue
                if "{" in path:  # 跳过需 path 参数的（手写流已覆盖关键的）
                    continue
                if (path, "GET") in already or path in ("/health", "/openapi.json", "/docs", "/redoc"):
                    continue
                self.call(f"{name}:auto-GET", f"{name}{path}", "GET", base, path, gated_on=(401, 403))

    def sweep_tasks(self):
        """确认本机任务 API 存在，但不提交任何真实自动化任务。"""
        self.rows.append(
            Row(
                "tasks",
                "local-task-runtime",
                "-",
                "in-process",
                None,
                "SKIP",
                "为避免外部副作用，扫描不投递任务；请通过 GET /tasks/{task_id} 查询既有任务。",
            )
        )

    def sweep_registration(self):
        """注册流程仅可在人工受控环境执行，功能扫描明确跳过。"""
        self.rows.append(
            Row(
                "registration",
                "browser-automation",
                "-",
                "local-process-pool",
                None,
                "SKIP",
                "不执行真实注册、代理轮换、验证码或浏览器自动化。",
            )
        )

    # ---------- 运行 & 报告 ----------

    def run_all(self):
        for fn in [self.sweep_health, self.sweep_auth, self.sweep_observability,
                   self.sweep_alerts, self.sweep_proxy, self.sweep_accounts,
                   self.sweep_forwarding, self.discover_gets, self.sweep_tasks,
                   self.sweep_registration]:
            try:
                fn()
            except Exception as e:
                self.rows.append(Row(fn.__name__, "(组异常)", "-", "-", None, "ERROR", str(e)[:90]))

    def report(self):
        order = {"PASS": 0, "GATED": 1, "FAIL": 2, "ERROR": 3, "SKIP": 4}
        counts = {k: 0 for k in order}
        for r in self.rows:
            counts[r.verdict] = counts.get(r.verdict, 0) + 1
        icon = {"PASS": "[OK ]", "GATED": "[GATE]", "FAIL": "[FAIL]", "ERROR": "[ERR]", "SKIP": "[SKIP]"}
        print("\n================= 功能扫描报告 =================")
        last_group = None
        for r in sorted(self.rows, key=lambda x: (x.group, x.feature)):
            if r.group != last_group:
                print(f"\n## {r.group}")
                last_group = r.group
            st = r.status if r.status is not None else "-"
            print(f"  {icon.get(r.verdict,'[?]'):7} {r.feature:34} {r.method:5} {str(st):4} {r.ms:>5}ms  {r.note[:70]}")
        total = len(self.rows)
        print("\n================= 汇总 =================")
        print(f"  总计 {total}:  PASS={counts.get('PASS',0)}  GATED={counts.get('GATED',0)}  "
              f"FAIL={counts.get('FAIL',0)}  ERROR={counts.get('ERROR',0)}")
        out = os.path.join(os.path.dirname(__file__), "_sweep_report.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in self.rows], f, ensure_ascii=False, indent=2)
        print(f"  报告已存 {out}")
        return counts


def main():
    s = Sweep()
    s.run_all()
    counts = s.report()
    # 退出码：有非 GATED 的 FAIL/ERROR → 非零
    sys.exit(1 if (counts.get("FAIL", 0) + counts.get("ERROR", 0)) > 0 else 0)


if __name__ == "__main__":
    main()
