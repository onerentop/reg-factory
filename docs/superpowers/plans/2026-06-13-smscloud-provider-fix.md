# SMS Cloud Provider 对齐官方 API 重写 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重写 `SmsCloudProvider` 使其与 SMS Cloud 官方 API 对齐（header `apiKey` 鉴权、`/public/sms/*` 端点、`{code,message,data}` 信封解析），修复「余额查询不对（恒为 0）」及取号/取码/取消/完成全部不可用的问题。

**Architecture:** 只改一个适配器文件 `services/sms_service/providers/sms_cloud.py`，沿用现有策略模式（`SMSProvider` 子类）+ 工厂（`ProviderRegistry`）。核心是把 `_get` 助手从「query api_key + 顶层取字段」改为「header apiKey + 校验 `code==0` + 返回 `data`」，五个方法换正确端点/字段。`base.py` 接口、`service.py`、其它 provider、DB 配置均不动。

**Tech Stack:** Python 3.13 · httpx(AsyncClient) · pytest + pytest-asyncio(asyncio_mode=auto) · httpx.MockTransport(测试，无需新依赖)

**测试运行约定（重要）：** 所有 `pytest` 命令在 `f:/reg-factory/services` 目录下执行（`pyproject.toml` 设了 `pythonpath=["."]`、`asyncio_mode="auto"`）。

**参考文档：** 设计 spec `docs/superpowers/specs/2026-06-13-smscloud-provider-fix-design.md`；官方 API 文档 `C:\Users\lenovo\Downloads\api\SMS Cloud API.html`。

---

## File Structure

- **Modify** `services/sms_service/providers/sms_cloud.py` —— 唯一生产改动。重写 `_get` + 5 个方法。`config_schema`/`_base_url`/`_api_key`/类注册不变。
- **Create** `services/tests/sms_service/test_sms_cloud_provider.py` —— 离线单元测试（httpx.MockTransport mock HTTP），覆盖 balance/错误信封/取号/取码/取消/完成。含一个测试内 helper `patch_http`，不放 conftest（避免污染其它测试）。
- **Create** `services/scripts/smscloud_smoke.py` —— 联网 smoke：用 DB 里真实 apiKey 打 `/public/sms/balance`，断言 `code==0` 且 `data.balance` 是数字。手动运行，不进 CI。

---

## Task 1: 重写 `_get` 助手 + `get_balance`（header 鉴权 + 信封解析 + 错误浮现）

**Files:**
- Create: `services/tests/sms_service/test_sms_cloud_provider.py`
- Modify: `services/sms_service/providers/sms_cloud.py:33-44`（`_get` 与 `get_balance`）

- [ ] **Step 1: 写失败测试**（新建测试文件，含 helper + 3 个 balance/错误测试）

创建 `services/tests/sms_service/test_sms_cloud_provider.py`：

```python
"""SmsCloudProvider 单元测试。用 httpx.MockTransport mock 真实 HTTP，
断言鉴权头(apiKey)、端点路径、信封解析(data.*)、错误(code!=0)抛异常。"""
import asyncio

import httpx
import pytest

from sms_service.providers.sms_cloud import SmsCloudProvider
from sms_service.providers.base import OrderStatus

API = "https://smscloud.sbs/api/system"


def patch_http(monkeypatch, handler):
    """把 httpx.AsyncClient 换成带 MockTransport(handler) 的版本。
    handler(request)->httpx.Response，可借 request 断言 headers/url/params。"""
    real_client = httpx.AsyncClient  # 先抓原始构造器，避免 fake 内部递归调到自己
    def fake_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", fake_client)


def provider():
    return SmsCloudProvider({"api_key": "K123", "base_url": API})


async def test_get_balance_parses_data_balance(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, json={"code": 0, "message": "操作成功", "data": {"balance": 8.0}})

    patch_http(monkeypatch, handler)
    bal = await provider().get_balance()
    assert bal == 8.0


async def test_get_balance_sends_apikey_header_and_correct_endpoint(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, json={"code": 0, "message": "", "data": {"balance": 1.0}})

    patch_http(monkeypatch, handler)
    await provider().get_balance()
    assert captured["req"].headers["apiKey"] == "K123"
    assert captured["req"].url.path.endswith("/public/sms/balance")


async def test_error_envelope_raises_valueerror(monkeypatch):
    def handler(req):
        return httpx.Response(200, json={"code": 40001, "message": "登录凭证已过期", "data": None})

    patch_http(monkeypatch, handler)
    with pytest.raises(ValueError, match="40001"):
        await provider().get_balance()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/test_sms_cloud_provider.py -v`
Expected: FAIL —— 现有 `_get` 用 query `api_key` 且 `get_balance` 取顶层 `result["balance"]`，无 apiKey header（`test_..._apikey_header` KeyError/AssertionError），且不检查 code（`test_error_envelope` 不抛异常反而返回 0.0）。

- [ ] **Step 3: 重写 `_get` 与 `get_balance`**

在 `services/sms_service/providers/sms_cloud.py` 中，将现有 `_get`（33-40 行）和 `get_balance`（42-44 行）替换为：

```python
    async def _get(self, path: str, params: dict | None = None) -> dict:
        """GET {base_url}{path}，header 带 apiKey；校验信封 code==0 后返回 data。"""
        async with httpx.AsyncClient(
            timeout=30, headers={"apiKey": self._api_key}
        ) as client:
            resp = await client.get(f"{self._base_url}{path}", params=params or {})
            resp.raise_for_status()
            body = resp.json()
        if body.get("code") != 0:
            raise ValueError(f"SMS Cloud {body.get('code')}: {body.get('message')}")
        return body.get("data") or {}

    async def get_balance(self) -> float:
        data = await self._get("/public/sms/balance")
        return float(data.get("balance", 0))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/test_sms_cloud_provider.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
cd f:/reg-factory && git add services/sms_service/providers/sms_cloud.py services/tests/sms_service/test_sms_cloud_provider.py && git commit -F - <<'EOF'
fix(sms_cloud): _get 改 header apiKey 鉴权 + 信封校验，get_balance 取 data.balance

修复余额恒为 0：旧代码 query api_key + 顶层取 balance + 不判 code，
错误被静默吞成 0。改为 header apiKey、校验 code==0(否则抛 ValueError)、
端点 /public/sms/balance、取 data.balance。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## Task 2: `get_number` 对齐 `/public/sms/getNumber`（参数 serviceCode/countryCode，映射 data.id/phoneNumber）

**Files:**
- Modify: `services/sms_service/providers/sms_cloud.py:46-57`（`get_number`）
- Modify: `services/tests/sms_service/test_sms_cloud_provider.py`（追加测试）

- [ ] **Step 1: 写失败测试**（追加到测试文件末尾）

```python
async def test_get_number_maps_fields_and_params(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, json={"code": 0, "message": "", "data": {
            "id": "2046386613387407360",
            "serviceCode": "tg",
            "countryCode": "44",
            "phoneNumber": "447700900123",
            "creditAmount": 3.2,
        }})

    patch_http(monkeypatch, handler)
    res = await provider().get_number("tg", "44")
    assert res.order_id == "2046386613387407360"
    assert res.phone_number == "447700900123"
    assert res.provider == "sms_cloud"
    assert captured["req"].url.path.endswith("/public/sms/getNumber")
    q = dict(captured["req"].url.params)
    assert q["serviceCode"] == "tg"
    assert q["countryCode"] == "44"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/test_sms_cloud_provider.py::test_get_number_maps_fields_and_params -v`
Expected: FAIL —— 旧 `get_number` 打 `/get_number`、传 `service_code`/`country`、读 `result["phone"]`（`data` 里无 `phone`，且端点路径不符）。

- [ ] **Step 3: 重写 `get_number`**

将 `services/sms_service/providers/sms_cloud.py` 的 `get_number`（46-57 行）替换为：

```python
    async def get_number(self, service: str, country: str) -> AcquireResult:
        data = await self._get("/public/sms/getNumber", {
            "serviceCode": service,
            "countryCode": country,
        })
        return AcquireResult(
            order_id=str(data["id"]),
            phone_number=data["phoneNumber"],
            provider=self.name,
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/test_sms_cloud_provider.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
cd f:/reg-factory && git add services/sms_service/providers/sms_cloud.py services/tests/sms_service/test_sms_cloud_provider.py && git commit -F - <<'EOF'
fix(sms_cloud): get_number 对齐 /public/sms/getNumber，serviceCode/countryCode + data.id/phoneNumber

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## Task 3: `get_code` 轮询 `/public/sms/orders/sync/{id}`（data.code 命中 / 超时）

**Files:**
- Modify: `services/sms_service/providers/sms_cloud.py:59-72`（`get_code`）
- Modify: `services/tests/sms_service/test_sms_cloud_provider.py`（追加测试）

- [ ] **Step 1: 写失败测试**（追加到测试文件末尾）

```python
async def test_get_code_received(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, json={"code": 0, "message": "", "data": {
            "id": "175847584743", "code": "123456",
            "text": "Your verification code is 123456", "dateTime": 1776316890,
        }})

    patch_http(monkeypatch, handler)
    res = await provider().get_code("175847584743", timeout=10)
    assert res.code == "123456"
    assert res.status == OrderStatus.RECEIVED
    assert captured["req"].url.path.endswith("/public/sms/orders/sync/175847584743")


async def test_get_code_timeout_when_code_empty(monkeypatch):
    async def fast_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    def handler(req):
        return httpx.Response(200, json={"code": 0, "message": "", "data": {"id": "1", "code": None}})

    patch_http(monkeypatch, handler)
    res = await provider().get_code("1", timeout=10)
    assert res.code is None
    assert res.status == OrderStatus.TIMEOUT
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/test_sms_cloud_provider.py -k get_code -v`
Expected: FAIL —— 旧 `get_code` 打 `/get_code` + query `order_id`，端点路径不符（`orders/sync/{id}` 断言失败）。

- [ ] **Step 3: 重写 `get_code`**

将 `services/sms_service/providers/sms_cloud.py` 的 `get_code`（59-72 行）替换为：

```python
    async def get_code(self, order_id: str, timeout: int = 120) -> CodeResult:
        elapsed = 0
        interval = 5
        while elapsed < timeout:
            data = await self._get(f"/public/sms/orders/sync/{order_id}")
            code = data.get("code")
            if code:
                return CodeResult(order_id=order_id, code=code, status=OrderStatus.RECEIVED)
            await asyncio.sleep(interval)
            elapsed += interval
        return CodeResult(order_id=order_id, code=None, status=OrderStatus.TIMEOUT)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/test_sms_cloud_provider.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
cd f:/reg-factory && git add services/sms_service/providers/sms_cloud.py services/tests/sms_service/test_sms_cloud_provider.py && git commit -F - <<'EOF'
fix(sms_cloud): get_code 轮询 /public/sms/orders/sync/{id} 读 data.code

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## Task 4: `complete`/`cancel` 对齐 `orders/finish/{id}`、`orders/cancel/{id}`

**Files:**
- Modify: `services/sms_service/providers/sms_cloud.py:74-78`（`complete`、`cancel`）
- Modify: `services/tests/sms_service/test_sms_cloud_provider.py`（追加测试）

- [ ] **Step 1: 写失败测试**（追加到测试文件末尾）

```python
async def test_complete_hits_finish_endpoint(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, json={"code": 0, "message": "", "data": {}})

    patch_http(monkeypatch, handler)
    await provider().complete("oid9")
    assert captured["req"].url.path.endswith("/public/sms/orders/finish/oid9")


async def test_cancel_hits_cancel_endpoint(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, json={"code": 0, "message": "", "data": {}})

    patch_http(monkeypatch, handler)
    await provider().cancel("oid9")
    assert captured["req"].url.path.endswith("/public/sms/orders/cancel/oid9")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/test_sms_cloud_provider.py -k "complete or cancel" -v`
Expected: FAIL —— 旧 `complete`/`cancel` 打 `/complete`、`/cancel` + query `order_id`，端点路径不符。

- [ ] **Step 3: 重写 `complete`/`cancel`**

将 `services/sms_service/providers/sms_cloud.py` 的 `complete`（74-75 行）与 `cancel`（77-78 行）替换为：

```python
    async def complete(self, order_id: str) -> None:
        await self._get(f"/public/sms/orders/finish/{order_id}")

    async def cancel(self, order_id: str) -> None:
        await self._get(f"/public/sms/orders/cancel/{order_id}")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/test_sms_cloud_provider.py -v`
Expected: PASS（8 passed）

- [ ] **Step 5: 提交**

```bash
cd f:/reg-factory && git add services/sms_service/providers/sms_cloud.py services/tests/sms_service/test_sms_cloud_provider.py && git commit -F - <<'EOF'
fix(sms_cloud): complete/cancel 对齐 orders/finish|cancel/{id}

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## Task 5: 联网 smoke 脚本 + 全量回归

**Files:**
- Create: `services/scripts/smscloud_smoke.py`

- [ ] **Step 1: 写 smoke 脚本**

创建 `services/scripts/smscloud_smoke.py`：

```python
"""SMS Cloud 联网 smoke：用 sms.db 里真实 apiKey 打余额接口，验证协议对齐。
手动运行(需联网+有效密钥)，不进 CI。
  cd f:/reg-factory/services && python scripts/smscloud_smoke.py
"""
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sms_service.providers.sms_cloud import SmsCloudProvider  # noqa: E402


def _load_config() -> dict:
    db = Path(__file__).resolve().parents[1] / "sms.db"
    con = sqlite3.connect(str(db))
    try:
        row = con.execute(
            "SELECT config FROM sms_platform_configs WHERE provider_name='sms_cloud'"
        ).fetchone()
    finally:
        con.close()
    if not row:
        raise SystemExit("sms_cloud 未在 sms.db 配置")
    return json.loads(row[0])


async def main() -> int:
    provider = SmsCloudProvider(_load_config())
    balance = await provider.get_balance()
    print(f"OK: sms_cloud balance = {balance}")
    assert isinstance(balance, float)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 2: 跑 smoke（联网）确认拿到真实余额**

Run: `cd f:/reg-factory/services && python scripts/smscloud_smoke.py`
Expected: 打印 `OK: sms_cloud balance = 8.0`（数值随真实账户变化，关键是非 0 且不抛 `SMS Cloud 40001` 错误）。
注：smscloud.sbs 直连偶发超时，失败重跑一次即可。

- [ ] **Step 3: 全量回归（确认未破坏其它 sms 测试）**

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/ -v`
Expected: PASS —— 新增 8 个 + 原有 `test_provider_registry`/`test_sms_routes`/`test_firefox_fun` 全绿。

- [ ] **Step 4: 提交**

```bash
cd f:/reg-factory && git add services/scripts/smscloud_smoke.py && git commit -F - <<'EOF'
test(sms_cloud): 联网 smoke 脚本，用真实密钥验证余额接口对齐

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## Self-Review

**1. Spec coverage（逐 spec 节核对）：**
- spec §1 根因三处错（鉴权/端点/解析）→ Task 1 `_get`+`get_balance` 全覆盖 ✅
- spec §2 协议表：balance→T1，getNumber→T2，orders/sync→T3，cancel/finish→T4 ✅
- spec §3.1 `_get`（header apiKey + code 校验 + 返回 data）→ T1 代码一致 ✅
- spec §3.2 五方法 → T1(balance)/T2(number)/T3(code)/T4(complete,cancel) ✅
- spec §4 测试：6 类单元（balance 解析/apiKey 头/错误信封/getNumber 字段/get_code 命中+超时/complete+cancel 端点）→ T1-T4 共 8 测试覆盖；联网 smoke → T5 ✅
- spec §5 非目标（不改 base/service/其它 provider/replace 等）→ 计划仅改 sms_cloud.py + 新增测试/脚本，未触碰 ✅

**2. Placeholder scan：** 无 TBD/TODO；每个代码步骤均给完整代码与确切命令。✅

**3. Type consistency：** `provider()` helper、`patch_http`、`AcquireResult(order_id/phone_number/provider)`、`CodeResult(order_id/code/status)`、`OrderStatus.RECEIVED/TIMEOUT`、`_get(path, params)` 在各 task 一致；provider 名 `"sms_cloud"`（由 `@ProviderRegistry.register("sms_cloud")` 注入 `self.name`）→ T2 断言 `res.provider == "sms_cloud"` 一致。✅
