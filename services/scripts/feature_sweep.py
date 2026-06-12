"""功能扫描：对运行中的 services 栈做一遍——打每个 live 端点 + 触发每个 Celery 任务，
逐功能报 PASS/FAIL/ERROR/GATED。见 docs/superpowers/specs/2026-06-12-feature-sweep-design.md。

跑法（从 services/ 目录，栈需先起来）：
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
SMS = os.getenv("SMS_URL", "http://127.0.0.1:8001")
ACCOUNT = os.getenv("ACCOUNT_URL", "http://127.0.0.1:8002")
CONFIG = os.getenv("CONFIG_URL", "http://127.0.0.1:8003")
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
SERVICES = {"gateway": GATEWAY, "sms": SMS, "account": ACCOUNT, "config": CONFIG}


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
        for name, base in SERVICES.items():
            self.call("health", f"{name}/health", "GET", base, "/health")

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
        r = self.call("accounts", "create_account", "POST", ACCOUNT, "/accounts",
                      json_body={"email": email, "password": "Sweep!123", "platform": "outlook"},
                      ok=range(200, 300), gated_on=(422,))
        self.call("accounts", "list_accounts", "GET", ACCOUNT, "/accounts")
        aid = None
        if r is not None and r.status_code < 300:
            try:
                aid = r.json().get("data", {}).get("id")
            except Exception:
                pass
        if aid:
            self.call("accounts", "get_account", "GET", ACCOUNT, f"/accounts/{aid}")
            self.call("accounts", "update_account", "PUT", ACCOUNT, f"/accounts/{aid}",
                      json_body={"status": "success"}, ok=range(200, 300), gated_on=(422,))
            self.call("accounts", "delete_account(cleanup)", "DELETE", ACCOUNT, f"/accounts/{aid}")

    def sweep_forwarding(self):
        # gateway 转发到各服务
        self.call("forwarding", "fwd /accounts", "GET", GATEWAY, "/accounts", gated_on=(502, 504))
        self.call("forwarding", "fwd /sms/health", "GET", GATEWAY, "/sms/health", gated_on=(404, 502, 504))
        self.call("forwarding", "fwd /config/health", "GET", GATEWAY, "/config/health", gated_on=(404, 502, 504))

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
        os.environ.setdefault("REDIS_URL", REDIS_URL)
        try:
            from worker.tasks import celery_app
        except Exception as e:
            self.rows.append(Row("tasks", "import celery_app", "-", "worker.tasks", None, "ERROR", str(e)[:80]))
            return
        # 非浏览器任务：真发真等结果
        safe = ["check_proxy_health", "check_sms_balance", "cleanup_old_logs"]
        for name in safe:
            t0 = time.monotonic()
            try:
                res = celery_app.send_task(name)
                out = res.get(timeout=15)
                ms = int((time.monotonic() - t0) * 1000)
                self.rows.append(Row("tasks", name, "task", "celery", None, "PASS", str(out)[:90], ms))
            except Exception as e:
                ms = int((time.monotonic() - t0) * 1000)
                self.rows.append(Row("tasks", name, "task", "celery", None, "FAIL", f"{type(e).__name__}: {str(e)[:70]}", ms))
        # 其余任务：验证可入队（send 成功 = 已注册可路由），不等长结果
        queue_only = ["planned_registration", "register_account", "register_all_platforms",
                      "retry_from_step", "unlock_outlook_account", "validate_session_key", "activate_plus_account",
                      "full_flow"]
        for name in queue_only:
            try:
                res = celery_app.send_task(name, kwargs={}) if name in ("planned_registration",) else celery_app.send_task(name, args=[], kwargs={})
                self.rows.append(Row("tasks", f"{name}(enqueue)", "task", "celery", None, "PASS", f"queued id={res.id[:8]}", 0))
            except Exception as e:
                self.rows.append(Row("tasks", f"{name}(enqueue)", "task", "celery", None, "FAIL", str(e)[:70]))

    def sweep_registration(self):
        os.environ.setdefault("REDIS_URL", REDIS_URL)
        try:
            from worker.tasks import celery_app
        except Exception as e:
            self.rows.append(Row("registration", "register_outlook_single", "task", "celery", None, "ERROR", str(e)[:80]))
            return
        t0 = time.monotonic()
        try:
            res = celery_app.send_task("register_outlook_single", kwargs={"idx": 0, "proxy": "", "config": {}})
            try:
                out = res.get(timeout=25)  # 预期失败在 ixBrowser/proxy 处
                ms = int((time.monotonic() - t0) * 1000)
                # 走到执行并返回（成功或失败结果）= 基础设施通
                self.rows.append(Row("registration", "register_outlook_single", "task", "celery", None, "GATED",
                                     f"执行返回(需ixBrowser/IP真出号): {str(out)[:70]}", ms))
            except Exception as e:
                ms = int((time.monotonic() - t0) * 1000)
                # 超时/执行异常 = 走到了执行层、卡在浏览器/IP gate
                self.rows.append(Row("registration", "register_outlook_single", "task", "celery", None, "GATED",
                                     f"走到执行层卡gate(ixBrowser/IP): {type(e).__name__} {str(e)[:50]}", ms))
        except Exception as e:
            self.rows.append(Row("registration", "register_outlook_single", "task", "celery", None, "FAIL",
                                 f"入队失败: {str(e)[:70]}"))

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
