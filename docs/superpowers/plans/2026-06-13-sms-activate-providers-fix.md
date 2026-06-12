# SMS-Activate 系 Provider（hero/sms_bower）抽基类重写 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 抽 `SmsActivateProvider` 基类封装 SMS-Activate `handler_api.php` 纯文本协议，hero_sms 与 sms_bower 继承共用；修复 sms_bower 现状用不存在的 REST 端点(404)，并修正其 DB base_url。

**Architecture:** 新增基类文件 `sms_activate_base.py`（模板方法：基类定义协议骨架，子类只配 host），hero_sms/sms_bower 改为薄子类。沿用现有策略（`SMSProvider`）+ 工厂（`ProviderRegistry`）。base.py 接口、service.py、sms_cloud 均不动。

**Tech Stack:** Python 3.13 · httpx(AsyncClient) · pytest + pytest-asyncio(asyncio_mode=auto) · httpx.MockTransport(测试)

**测试运行约定：** 所有 `pytest`/`python` 命令在 `f:/reg-factory/services` 目录执行（`pyproject.toml` 设了 `pythonpath=["."]`、`asyncio_mode="auto"`）。

**分支：** 直接在 `main` 上执行（用户已确认）。

**参考：** spec `docs/superpowers/specs/2026-06-13-sms-activate-providers-fix-design.md`。

---

## File Structure

- **Create** `services/sms_service/providers/sms_activate_base.py` —— `SmsActivateProvider(SMSProvider)` 基类，handler_api 协议全部逻辑。
- **Rewrite** `services/sms_service/providers/hero_sms.py` —— 薄子类（继承基类，配 hero host）。
- **Rewrite** `services/sms_service/providers/sms_bower.py` —— 薄子类（从错误 REST 改成继承基类，配 sms_bower host）。
- **Create** `services/tests/sms_service/test_sms_activate_base.py` —— 基类逻辑单测（MockTransport mock 纯文本，用测试桩 `_P`）。
- **Create** `services/tests/sms_service/test_sms_activate_subclasses.py` —— hero/sms_bower 子类配置测（注册名/base_url/display_name）。
- **Create** `services/scripts/fix_sms_bower_baseurl.py` —— 一次性 DB 修复（sms_bower base_url → handler_api.php，保留 api_key）。
- **Create** `services/scripts/sms_activate_smoke.py` —— 联网 smoke（两家 getBalance）。

---

## Task 1: `SmsActivateProvider` 基类（handler_api 协议）

**Files:**
- Create: `services/tests/sms_service/test_sms_activate_base.py`
- Create: `services/sms_service/providers/sms_activate_base.py`

- [ ] **Step 1: 写失败测试**（建测试文件，含 helper + 测试桩 + 10 用例）

创建 `services/tests/sms_service/test_sms_activate_base.py`：

```python
"""SmsActivateProvider 基类单测。MockTransport mock handler_api 纯文本响应。
用测试桩 _P 隔离基类逻辑，不依赖具体平台。"""
import asyncio

import httpx
import pytest

from sms_service.providers.sms_activate_base import SmsActivateProvider
from sms_service.providers.base import OrderStatus


def patch_http(monkeypatch, handler):
    """把 httpx.AsyncClient 换成带 MockTransport(handler) 的版本。
    先抓原始构造器，避免 fake 内部递归调到自己。"""
    real_client = httpx.AsyncClient
    def fake_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return real_client(*args, transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", fake_client)


class _P(SmsActivateProvider):
    name = "testp"
    _default_base_url = "https://x.test/handler_api.php"


def provider():
    return _P({"api_key": "K123"})


async def test_get_balance_parses(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, text="ACCESS_BALANCE:1.1947"))
    assert await provider().get_balance() == 1.1947


async def test_get_balance_error_raises(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, text="BAD_KEY"))
    with pytest.raises(ValueError, match="BAD_KEY"):
        await provider().get_balance()


async def test_request_sends_apikey_and_action(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, text="ACCESS_BALANCE:1")

    patch_http(monkeypatch, handler)
    await provider().get_balance()
    q = dict(captured["req"].url.params)
    assert q["api_key"] == "K123"
    assert q["action"] == "getBalance"


async def test_get_number_parses(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, text="ACCESS_NUMBER:12345:79001234567")

    patch_http(monkeypatch, handler)
    res = await provider().get_number("tg", "0")
    assert res.order_id == "12345"
    assert res.phone_number == "79001234567"
    assert res.provider == "testp"
    q = dict(captured["req"].url.params)
    assert q["action"] == "getNumber"
    assert q["service"] == "tg"
    assert q["country"] == "0"


async def test_get_number_error_raises(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, text="NO_NUMBERS"))
    with pytest.raises(ValueError, match="NO_NUMBERS"):
        await provider().get_number("tg", "0")


async def test_get_code_received(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, text="STATUS_OK:654321")

    patch_http(monkeypatch, handler)
    res = await provider().get_code("999", timeout=10)
    assert res.code == "654321"
    assert res.status == OrderStatus.RECEIVED
    q = dict(captured["req"].url.params)
    assert q["action"] == "getStatus"
    assert q["id"] == "999"


async def test_get_code_cancelled(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, text="STATUS_CANCEL"))
    res = await provider().get_code("999", timeout=10)
    assert res.code is None
    assert res.status == OrderStatus.CANCELLED


async def test_get_code_timeout(monkeypatch):
    async def fast_sleep(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    patch_http(monkeypatch, lambda req: httpx.Response(200, text="STATUS_WAIT_CODE"))
    res = await provider().get_code("999", timeout=10)
    assert res.code is None
    assert res.status == OrderStatus.TIMEOUT


async def test_complete_sets_status_6(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, text="ACCESS_ACTIVATION")

    patch_http(monkeypatch, handler)
    await provider().complete("999")
    q = dict(captured["req"].url.params)
    assert q["action"] == "setStatus"
    assert q["id"] == "999"
    assert q["status"] == "6"


async def test_cancel_sets_status_8(monkeypatch):
    captured = {}

    def handler(req):
        captured["req"] = req
        return httpx.Response(200, text="ACCESS_CANCEL")

    patch_http(monkeypatch, handler)
    await provider().cancel("999")
    q = dict(captured["req"].url.params)
    assert q["action"] == "setStatus"
    assert q["id"] == "999"
    assert q["status"] == "8"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/test_sms_activate_base.py -v`
Expected: FAIL（collection error: `ModuleNotFoundError: No module named 'sms_service.providers.sms_activate_base'`）。

- [ ] **Step 3: 写基类实现**

创建 `services/sms_service/providers/sms_activate_base.py`：

```python
import asyncio

import httpx

from sms_service.providers.base import (
    SMSProvider,
    AcquireResult,
    CodeResult,
    OrderStatus,
)


class SmsActivateProvider(SMSProvider):
    """SMS-Activate handler_api.php 协议基类（模板方法）。
    GET {base_url}?api_key=X&action=Y → 'ACCESS_*'/'STATUS_*' 纯文本。
    子类只需声明 display_name / _default_base_url / config_schema。"""

    _default_base_url: str = ""

    @property
    def _base_url(self) -> str:
        return self._config.get("base_url", self._default_base_url)

    @property
    def _api_key(self) -> str:
        return self._config.get("api_key", "")

    async def _request(self, params: dict) -> str:
        params["api_key"] = self._api_key
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self._base_url, params=params)
            resp.raise_for_status()
            return resp.text

    async def get_balance(self) -> float:
        text = await self._request({"action": "getBalance"})
        if text.startswith("ACCESS_BALANCE"):
            return float(text.split(":")[1])
        raise ValueError(f"{self.name} getBalance failed: {text}")

    async def get_number(self, service: str, country: str) -> AcquireResult:
        text = await self._request({
            "action": "getNumber", "service": service, "country": country,
        })
        if not text.startswith("ACCESS_NUMBER"):
            raise ValueError(f"{self.name} getNumber failed: {text}")
        parts = text.split(":")
        return AcquireResult(order_id=parts[1], phone_number=parts[2], provider=self.name)

    async def get_code(self, order_id: str, timeout: int = 120) -> CodeResult:
        elapsed = 0
        interval = 5
        while elapsed < timeout:
            text = await self._request({"action": "getStatus", "id": order_id})
            if text.startswith("STATUS_OK"):
                return CodeResult(order_id=order_id, code=text.split(":")[1], status=OrderStatus.RECEIVED)
            if text == "STATUS_CANCEL":
                return CodeResult(order_id=order_id, code=None, status=OrderStatus.CANCELLED)
            await asyncio.sleep(interval)
            elapsed += interval
        return CodeResult(order_id=order_id, code=None, status=OrderStatus.TIMEOUT)

    async def complete(self, order_id: str) -> None:
        await self._request({"action": "setStatus", "id": order_id, "status": "6"})

    async def cancel(self, order_id: str) -> None:
        await self._request({"action": "setStatus", "id": order_id, "status": "8"})
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/test_sms_activate_base.py -v`
Expected: PASS（10 passed）

- [ ] **Step 5: 提交**

```bash
cd f:/reg-factory && git add services/sms_service/providers/sms_activate_base.py services/tests/sms_service/test_sms_activate_base.py && git commit -F - <<'EOF'
feat(sms): SmsActivateProvider 基类封装 handler_api 纯文本协议

模板方法基类：query api_key+action → ACCESS_*/STATUS_* 解析。
balance/number/code(轮询 getStatus)/complete(setStatus 6)/cancel(setStatus 8)。
10 个基类逻辑单测(MockTransport mock 纯文本)。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## Task 2: 重写 `hero_sms.py` 为薄子类 + 子类配置测试

**Files:**
- Rewrite: `services/sms_service/providers/hero_sms.py`（全文替换，原 84 行 → 继承基类）
- Create: `services/tests/sms_service/test_sms_activate_subclasses.py`

- [ ] **Step 1: 写失败测试**（建子类配置测试文件，先放 hero 用例）

创建 `services/tests/sms_service/test_sms_activate_subclasses.py`：

```python
"""hero_sms / sms_bower 子类配置测：注册名、默认 base_url、display_name。
直接实例化子类(register 装饰器在 import 时已注入 name)，不需要 mock HTTP。"""
from sms_service.providers.hero_sms import HeroSmsProvider


def test_hero_config():
    p = HeroSmsProvider({"api_key": "k"})
    assert p.name == "hero_sms"
    assert p.display_name == "HeroSMS"
    assert p._base_url == "https://hero-sms.com/stubs/handler_api.php"


def test_hero_config_base_url_override():
    p = HeroSmsProvider({"api_key": "k", "base_url": "https://custom/handler_api.php"})
    assert p._base_url == "https://custom/handler_api.php"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/test_sms_activate_subclasses.py -v`
Expected: FAIL —— 现 `HeroSmsProvider` 仍是旧独立实现（无 `_default_base_url`，`_base_url` 取自 `_config.get("base_url", "https://hero-sms.com/stubs/handler_api.php")` 恰巧也对，但 `test_hero_config` 的 `_base_url` 可能已通过）。真正会失败的是导入后行为——若旧类已有正确 base_url，此 task 的红点在 Step 3 重写后通过基类继承验证。先运行确认当前状态；若 2 个用例已 PASS（旧实现 base_url 恰好对），仍执行 Step 3 完成继承重构（消除重复代码），并在 Step 4 复跑确认。

- [ ] **Step 3: 重写 `hero_sms.py`**（整文件替换）

将 `services/sms_service/providers/hero_sms.py` 全文替换为：

```python
from sms_service.providers.base import ProviderRegistry
from sms_service.providers.sms_activate_base import SmsActivateProvider


@ProviderRegistry.register("hero_sms")
class HeroSmsProvider(SmsActivateProvider):
    display_name = "HeroSMS"
    _default_base_url = "https://hero-sms.com/stubs/handler_api.php"
    config_schema = {
        "api_key": {"type": "string", "label": "API Key", "required": True},
        "base_url": {
            "type": "string",
            "label": "API Base URL",
            "default": "https://hero-sms.com/stubs/handler_api.php",
        },
    }
```

- [ ] **Step 4: 跑测试确认通过**（含全量 sms 回归，确认重构没破坏注册）

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/ -v`
Expected: PASS（hero 子类测 2 + 基类 10 + 原有 sms 测试全绿）

- [ ] **Step 5: 提交**

```bash
cd f:/reg-factory && git add services/sms_service/providers/hero_sms.py services/tests/sms_service/test_sms_activate_subclasses.py && git commit -F - <<'EOF'
refactor(hero_sms): 改继承 SmsActivateProvider 基类，去重复(行为不变)

hero 现状 handler_api 协议实测已对，重构为薄子类消除与 sms_bower 的重复，
补子类配置测试兜底。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## Task 3: 重写 `sms_bower.py` 为薄子类 + 子类配置测试

**Files:**
- Rewrite: `services/sms_service/providers/sms_bower.py`（全文替换，原 88 行 REST 实现 → 继承基类）
- Modify: `services/tests/sms_service/test_sms_activate_subclasses.py`（追加 sms_bower 用例）

- [ ] **Step 1: 写失败测试**（追加到 subclasses 测试文件末尾）

在 `services/tests/sms_service/test_sms_activate_subclasses.py` 顶部 import 后追加 import 与用例：

文件顶部 import 区改为：
```python
from sms_service.providers.hero_sms import HeroSmsProvider
from sms_service.providers.sms_bower import SmsBowerProvider
```

文件末尾追加：
```python
def test_bower_config():
    p = SmsBowerProvider({"api_key": "k"})
    assert p.name == "sms_bower"
    assert p.display_name == "SmsBower"
    assert p._base_url == "https://smsbower.com/stubs/handler_api.php"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/test_sms_activate_subclasses.py::test_bower_config -v`
Expected: FAIL —— 现 `SmsBowerProvider._base_url` 默认 `https://smsbower.com/api`（旧 REST），断言 `…/stubs/handler_api.php` 失败。

- [ ] **Step 3: 重写 `sms_bower.py`**（整文件替换）

将 `services/sms_service/providers/sms_bower.py` 全文替换为：

```python
from sms_service.providers.base import ProviderRegistry
from sms_service.providers.sms_activate_base import SmsActivateProvider


@ProviderRegistry.register("sms_bower")
class SmsBowerProvider(SmsActivateProvider):
    display_name = "SmsBower"
    _default_base_url = "https://smsbower.com/stubs/handler_api.php"
    config_schema = {
        "api_key": {"type": "string", "label": "API Key", "required": True},
        "base_url": {
            "type": "string",
            "label": "API Base URL",
            "default": "https://smsbower.com/stubs/handler_api.php",
        },
    }
```

- [ ] **Step 4: 跑测试确认通过**（全量 sms 回归）

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/ -v`
Expected: PASS（基类 10 + 子类 3 + 原有 sms 测试全绿）

- [ ] **Step 5: 提交**

```bash
cd f:/reg-factory && git add services/sms_service/providers/sms_bower.py services/tests/sms_service/test_sms_activate_subclasses.py && git commit -F - <<'EOF'
fix(sms_bower): 改继承 SmsActivateProvider，从错误 REST 改对 handler_api

旧代码用不存在的 REST /api/balance + Bearer(404)，真实是 sms-activate
handler_api 纯文本协议。重写为薄子类，base_url 默认改 /stubs/handler_api.php。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## Task 4: 修 DB 数据（sms_bower base_url）

**Files:**
- Create: `services/scripts/fix_sms_bower_baseurl.py`

- [ ] **Step 1: 写 DB 修复脚本**

创建 `services/scripts/fix_sms_bower_baseurl.py`：

```python
"""一次性修复：sms.db 里 sms_bower 的 base_url 旧值 https://smsbower.com/api
改成 SMS-Activate handler_api 端点，保留 api_key。幂等可重跑。
  cd f:/reg-factory/services && python scripts/fix_sms_bower_baseurl.py
"""
import json
import sqlite3
from pathlib import Path

CORRECT = "https://smsbower.com/stubs/handler_api.php"


def main() -> int:
    db = Path(__file__).resolve().parents[1] / "sms.db"
    con = sqlite3.connect(str(db))
    try:
        row = con.execute(
            "SELECT config FROM sms_platform_configs WHERE provider_name='sms_bower'"
        ).fetchone()
        if not row:
            print("sms_bower 未在 sms.db 配置，跳过")
            return 0
        cfg = json.loads(row[0])
        old = cfg.get("base_url")
        cfg["base_url"] = CORRECT
        con.execute(
            "UPDATE sms_platform_configs SET config=? WHERE provider_name='sms_bower'",
            (json.dumps(cfg),),
        )
        con.commit()
        print(f"OK: sms_bower base_url {old!r} -> {CORRECT!r} (api_key 保留)")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 跑脚本改 DB**

Run: `cd f:/reg-factory/services && python scripts/fix_sms_bower_baseurl.py`
Expected: 打印 `OK: sms_bower base_url 'https://smsbower.com/api' -> 'https://smsbower.com/stubs/handler_api.php' (api_key 保留)`

- [ ] **Step 3: 验证 DB 已改**

Run: `cd f:/reg-factory/services && python -c "import sqlite3,json; con=sqlite3.connect('sms.db'); r=con.execute(\"SELECT config FROM sms_platform_configs WHERE provider_name='sms_bower'\").fetchone(); print(json.loads(r[0]))"`
Expected: 输出含 `'base_url': 'https://smsbower.com/stubs/handler_api.php'` 且 `'api_key'` 仍是原值。

- [ ] **Step 4: 提交**

```bash
cd f:/reg-factory && git add services/scripts/fix_sms_bower_baseurl.py && git commit -F - <<'EOF'
fix(sms_bower): DB 修复脚本，base_url 改 handler_api 端点(保留 api_key)

旧 DB 存 https://smsbower.com/api 会覆盖代码默认值，故必须改 DB。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## Task 5: 联网 smoke + 全量回归

**Files:**
- Create: `services/scripts/sms_activate_smoke.py`

- [ ] **Step 1: 写 smoke 脚本**

创建 `services/scripts/sms_activate_smoke.py`：

```python
"""SMS-Activate 系联网 smoke：用 sms.db 真实 key 打 hero + sms_bower 的
getBalance，验证 handler_api 协议对齐。手动运行(需联网+有效密钥)，不进 CI。
  cd f:/reg-factory/services && python scripts/sms_activate_smoke.py
"""
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sms_service.providers.hero_sms import HeroSmsProvider  # noqa: E402
from sms_service.providers.sms_bower import SmsBowerProvider  # noqa: E402


def _load(provider_name: str) -> dict:
    db = Path(__file__).resolve().parents[1] / "sms.db"
    con = sqlite3.connect(str(db))
    try:
        row = con.execute(
            "SELECT config FROM sms_platform_configs WHERE provider_name=?",
            (provider_name,),
        ).fetchone()
    finally:
        con.close()
    if not row:
        raise SystemExit(f"{provider_name} 未在 sms.db 配置")
    return json.loads(row[0])


async def main() -> int:
    for name, cls in (("hero_sms", HeroSmsProvider), ("sms_bower", SmsBowerProvider)):
        bal = await cls(_load(name)).get_balance()
        print(f"OK: {name} balance = {bal}")
        assert isinstance(bal, float) and bal >= 0
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 2: 跑 smoke（联网）确认两家余额**

Run: `cd f:/reg-factory/services && python scripts/sms_activate_smoke.py`
Expected: 打印两行 `OK: hero_sms balance = 1.19…` 与 `OK: sms_bower balance = 0.78…`（数值随真实账户变化，关键是非负 float 且不抛 `getBalance failed`）。
注：平台直连偶发超时，失败重跑一次即可。

- [ ] **Step 3: 全量 sms 回归**

Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/ -v`
Expected: PASS —— 基类 10 + 子类 3 + 原有 `test_provider_registry`/`test_sms_routes`/`test_firefox_fun`/`test_sms_cloud_provider` 全绿。

- [ ] **Step 4: 提交**

```bash
cd f:/reg-factory && git add services/scripts/sms_activate_smoke.py && git commit -F - <<'EOF'
test(sms): SMS-Activate 系联网 smoke，hero+sms_bower 真实余额验证

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## Self-Review

**1. Spec coverage（逐 spec 节核对）：**
- spec §1 根因（sms_bower 404 / hero 已对 / 同协议）→ Task 1 基类 + Task 3 sms_bower 重写 + Task 4 DB ✅
- spec §2 协议表（getBalance/getNumber/getStatus/setStatus 6,8）→ Task 1 基类方法逐一覆盖 + 测试 ✅
- spec §3.1 基类代码 → Task 1 Step 3 一致 ✅
- spec §3.2 hero 子类 → Task 2 ✅
- spec §3.3 sms_bower 子类 → Task 3 ✅
- spec §3.4 DB 修复（保留 api_key）→ Task 4 脚本读 cfg 改 base_url 保留 api_key ✅
- spec §4 测试（基类 10 用例 / 子类配置 / 联网 smoke）→ Task 1(10) + Task 2,3(子类 3) + Task 5(smoke) ✅
- spec §5 非目标（不改 sms_cloud/base.py/前端，不实现 getNumberV）→ 计划仅触碰 hero/sms_bower/基类/脚本/测试 ✅

**2. Placeholder scan：** 无 TBD/TODO；每步给完整代码与确切命令。Task 2 Step 2 的「红」说明已显式处理「旧 base_url 恰好对、测试可能先 PASS」的边界，非占位。✅

**3. Type consistency：** `SmsActivateProvider`、`_default_base_url`、`_base_url`/`_api_key`/`_request`、`AcquireResult(order_id/phone_number/provider)`、`CodeResult(order_id/code/status)`、`OrderStatus.RECEIVED/CANCELLED/TIMEOUT`、注册名 `hero_sms`/`sms_bower`、测试桩 `_P.name="testp"` 全程一致。patch_http 与 sms_cloud 测试同款（先抓 real_client）。✅
