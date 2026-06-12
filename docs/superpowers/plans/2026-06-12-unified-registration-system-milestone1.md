# 统一注册系统 · 里程碑1（地基）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `services/worker` 的注册流程演进为「Step 对象化契约 + 可注入共享能力接口 + LegacyBridgeStep」的地基，5 个平台 flow 全部转为 LegacyBridgeStep 列表（行为不变、基线保持绿）。

**Architecture:** 拆 `step_engine.py` 为 `flows/` 包（`base.py` 定义 `Step`/`StepResult`/`RegistrationFlow` 模板方法/`FlowRegistry`，一平台一文件）；新增 `capabilities/` 包（共享能力 ABC 接口 + `ServiceBundle` 依赖注入容器 + `LegacyBridgeStep` 工厂）。`step_engine.py` 降为向后兼容 re-export 壳，`tasks.py` 零改动。

**Tech Stack:** Python 3.13、`services/` 下 `pythonpath=["."]`、pytest + `asyncio_mode=auto`（async 测试无需装饰器）、dataclass、abc。

**测试运行约定：** 全部测试从 `services/` 目录跑：`cd services && python -m pytest tests/worker/<file> -v`。services 测试目录用 `__init__.py`（与项目根 tests 约定不同）。

**契约决策（重要）：** `RegistrationFlow.run(context, from_step=1)` 仍返回 `list[StepResult]`，且步骤通过 `context` 字典传递数据——与现有 `tasks.py` 消费方式完全一致，故 `tasks.py` 不改。仅 `get_steps()` 从 `list[str]` 变为 `list[Step]`，并移除 `execute_step`（各分支逻辑移入 Step 的可调用方法）。spec 中的 `RegistrationResult` 在本里程碑**不引入**（YAGNI——当前消费方用 `list[StepResult]`+context 已足够），留待后续需要富聚合结果时再加。

---

## 文件结构

**新建：**
- `services/worker/flows/__init__.py` — re-export 基类符号 + import 各平台模块触发注册
- `services/worker/flows/base.py` — `Step`、`StepFn`、`StepResult`、`RegistrationFlow`、`FlowRegistry`、`LegacyBridgeStep`
- `services/worker/flows/outlook.py` — `OutlookRegistrationFlow`
- `services/worker/flows/gmail.py` — `GmailRegistrationFlow`
- `services/worker/flows/claude.py` — `ClaudeRegistrationFlow`
- `services/worker/flows/chatgpt.py` — `ChatGptRegistrationFlow`
- `services/worker/flows/grok.py` — `GrokRegistrationFlow`
- `services/worker/capabilities/__init__.py` — re-export
- `services/worker/capabilities/interfaces.py` — 能力 ABC 接口 + 值对象
- `services/worker/capabilities/bundle.py` — `ServiceBundle`
- `services/tests/worker/test_flows_base.py`
- `services/tests/worker/test_capabilities_interfaces.py`
- `services/tests/worker/test_bundle.py`
- `services/tests/worker/test_outlook_flow.py`（取代 `test_step_engine_mode.py`）

**修改：**
- `services/worker/step_engine.py` — 清空为向后兼容 re-export 壳
- `services/tests/worker/test_step_engine_mode.py` — 删除（被 `test_outlook_flow.py` 取代）

**来源参考（要搬迁的现有代码）：** `services/worker/step_engine.py` 各 flow 的 `execute_step` 分支：Outlook(72-136)、Gmail(145-254)、Claude(259-323)、ChatGPT(328-401)、Grok(406-480)。`FlowRegistry`(482-末)。

---

## Task 1: flows/base.py —— Step 契约 + 模板方法 + FlowRegistry + LegacyBridgeStep

**Files:**
- Create: `services/worker/flows/base.py`
- Create: `services/worker/flows/__init__.py`
- Test: `services/tests/worker/test_flows_base.py`

- [ ] **Step 1: 写失败测试**

`services/tests/worker/test_flows_base.py`：
```python
import asyncio
from worker.flows.base import (
    Step, StepResult, RegistrationFlow, FlowRegistry, LegacyBridgeStep,
)


class _FakeFlow(RegistrationFlow):
    def __init__(self):
        # 不调用 super().__init__（避免 LegacyBridge），仅本测试用
        self.services = None
        self.calls = []

    def get_steps(self):
        async def s1(ctx, services):
            self.calls.append("s1"); ctx["a"] = 1
            return StepResult(success=True, data={"a": 1})

        async def s2(ctx, services):
            self.calls.append("s2")
            return StepResult(success=False, error="boom")

        async def s3(ctx, services):
            self.calls.append("s3")
            return StepResult(success=True)

        return [Step("one", s1), Step("two", s2), Step("three", s3)]


def test_run_executes_in_order_and_stops_on_failure():
    flow = _FakeFlow()
    results = asyncio.run(flow.run({}))
    assert flow.calls == ["s1", "s2"]            # s3 不执行（s2 失败短路）
    assert [r.success for r in results] == [True, False]
    assert results[0].step_number == 1 and results[0].name == "one"
    assert results[1].step_number == 2 and results[1].name == "two"
    assert results[1].error == "boom"
    assert results[0].duration_ms >= 0


def test_run_from_step_skips_earlier():
    flow = _FakeFlow()
    results = asyncio.run(flow.run({}, from_step=2))
    assert flow.calls == ["s2"]                  # s1 跳过
    assert results[0].step_number == 1 and results[0].success is True  # 跳过的记为成功占位


def test_step_exception_becomes_failed_result():
    class _Boom(RegistrationFlow):
        def __init__(self): self.services = None
        def get_steps(self):
            async def s(ctx, services): raise RuntimeError("kaboom")
            return [Step("x", s)]
    results = asyncio.run(_Boom().run({}))
    assert results[0].success is False and "kaboom" in results[0].error


def test_legacy_bridge_step_marks_kind_legacy():
    async def fn(ctx, services): return StepResult(success=True)
    step = LegacyBridgeStep("legacy-one", fn)
    assert isinstance(step, Step) and step.kind == "legacy" and step.name == "legacy-one"


def test_flow_registry_register_and_get():
    FlowRegistry.register("fake", _FakeFlow)
    flow = FlowRegistry.get("fake")
    assert isinstance(flow, _FakeFlow)


def test_flow_registry_unknown_raises():
    try:
        FlowRegistry.get("nope-platform")
        assert False, "should raise"
    except ValueError:
        pass
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services && python -m pytest tests/worker/test_flows_base.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'worker.flows'`）

- [ ] **Step 3: 实现 base.py**

`services/worker/flows/base.py`：
```python
"""注册流程地基：Step 对象化契约 + 模板方法 + 注册表 + 遗留桥接 Step。"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

# Step 可调用签名：(context, services) -> StepResult
StepFn = Callable[[dict, Any], Awaitable["StepResult"]]


@dataclass
class StepResult:
    success: bool
    name: str = ""
    step_number: int = 0
    error: str | None = None
    duration_ms: int = 0
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Step:
    """一个注册步骤：name + 可调用 run(context, services) -> StepResult。
    kind 用于迁移可观测性：'native'(原生共享服务) / 'legacy'(桥接遗留单体)。"""
    name: str
    run: StepFn
    kind: str = "native"


def LegacyBridgeStep(name: str, run: StepFn) -> Step:
    """工厂：包装遗留调用的 Step（kind='legacy'）。Strangler 迁移时整体替换为 native Step。"""
    return Step(name=name, run=run, kind="legacy")


class RegistrationFlow(ABC):
    """注册流程抽象基类。模板方法 run() 定义步骤执行骨架。

    services: 注入的 ServiceBundle（本里程碑各平台仍走 LegacyBridgeStep，可为 None）。
    """

    def __init__(self, services: Any = None):
        self.services = services
        # 让桥接的遗留 import 可用
        from worker.legacy_bridge import LegacyBridge
        self._bridge = LegacyBridge()
        self._bridge.ensure_importable()

    @abstractmethod
    def get_steps(self) -> list[Step]:
        ...

    async def run(self, context: dict, from_step: int = 1) -> list[StepResult]:
        steps = self.get_steps()
        results: list[StepResult] = []
        for i, step in enumerate(steps, 1):
            if i < from_step:
                results.append(StepResult(success=True, name=step.name, step_number=i, duration_ms=0))
                continue
            start = time.monotonic()
            try:
                result = await step.run(context, self.services)
                result.step_number = i
                result.name = step.name
                result.duration_ms = int((time.monotonic() - start) * 1000)
                results.append(result)
                if not result.success:
                    break
            except Exception as e:
                results.append(StepResult(
                    success=False, name=step.name, step_number=i,
                    error=str(e), duration_ms=int((time.monotonic() - start) * 1000),
                ))
                break
        return results


class FlowRegistry:
    """注册流程注册表。工厂模式。各平台模块 import 时调用 register() 登记自己。"""

    _flows: dict[str, type[RegistrationFlow]] = {}

    @classmethod
    def get(cls, platform: str) -> RegistrationFlow:
        flow_cls = cls._flows.get(platform)
        if flow_cls is None:
            raise ValueError(f"Unknown platform: {platform}")
        return flow_cls()

    @classmethod
    def register(cls, platform: str, flow_cls: type[RegistrationFlow]) -> None:
        cls._flows[platform] = flow_cls
```

`services/worker/flows/__init__.py`（本任务先只 re-export base；平台注册在 Task 9 补全）：
```python
from worker.flows.base import (
    Step, StepFn, StepResult, RegistrationFlow, FlowRegistry, LegacyBridgeStep,
)

__all__ = ["Step", "StepFn", "StepResult", "RegistrationFlow", "FlowRegistry", "LegacyBridgeStep"]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd services && python -m pytest tests/worker/test_flows_base.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add services/worker/flows/base.py services/worker/flows/__init__.py services/tests/worker/test_flows_base.py
git commit -m "feat(worker): flows/base.py —— Step契约+模板方法+FlowRegistry+LegacyBridgeStep"
```

---

## Task 2: capabilities/interfaces.py —— 共享能力 ABC 接口 + 值对象

**Files:**
- Create: `services/worker/capabilities/interfaces.py`
- Create: `services/worker/capabilities/__init__.py`
- Test: `services/tests/worker/test_capabilities_interfaces.py`

- [ ] **Step 1: 写失败测试**

`services/tests/worker/test_capabilities_interfaces.py`：
```python
import asyncio
import pytest
from worker.capabilities.interfaces import (
    BrowserSession, EmailAccount,
    BrowserService, ProxyService, CaptchaService, CaptchaResolver,
    EmailPoolService, SmsService, TokenExtractor,
)


@pytest.mark.parametrize("abc_cls", [
    BrowserService, ProxyService, CaptchaService,
    EmailPoolService, SmsService, TokenExtractor,
])
def test_abstract_cannot_instantiate(abc_cls):
    with pytest.raises(TypeError):
        abc_cls()


def test_value_objects_hold_fields():
    s = BrowserSession(page="p", context="c", profile_id="id", proxy="px")
    assert s.page == "p" and s.profile_id == "id"
    a = EmailAccount(email="e@x.com", password="pw")
    assert a.email == "e@x.com" and a.password == "pw" and a.refresh_token is None


def test_captcha_resolver_dispatches_by_kind():
    class _PX(CaptchaService):
        kind = "perimeterx"
        async def solve(self, page, context): return True

    resolver = CaptchaResolver()
    resolver.register(_PX())
    assert asyncio.run(resolver.solve("perimeterx", page=None, context={})) is True


def test_captcha_resolver_unknown_kind_raises():
    resolver = CaptchaResolver()
    with pytest.raises(KeyError):
        asyncio.run(resolver.solve("nope", page=None, context={}))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services && python -m pytest tests/worker/test_capabilities_interfaces.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'worker.capabilities'`）

- [ ] **Step 3: 实现 interfaces.py**

`services/worker/capabilities/interfaces.py`：
```python
"""共享能力服务接口（Strategy/Adapter）。具体实现在后续里程碑随平台迁移逐个落地。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class BrowserSession:
    """一次浏览器会话的值对象。"""
    page: Any
    context: Any
    profile_id: str
    proxy: str


@dataclass
class EmailAccount:
    """邮箱账号值对象。"""
    email: str
    password: str
    refresh_token: str | None = None
    client_id: str | None = None
    cookies: list | None = None


class BrowserService(ABC):
    @abstractmethod
    async def open(self, *, profile: str, proxy: str) -> BrowserSession: ...
    @abstractmethod
    async def close(self, session: BrowserSession) -> None: ...


class ProxyService(ABC):
    @abstractmethod
    def acquire(self) -> str: ...
    @abstractmethod
    def report(self, proxy: str, *, ok: bool) -> None: ...


class CaptchaService(ABC):
    """单一解法（Strategy）。子类设 kind 标识挑战类型。"""
    kind: str = ""
    @abstractmethod
    async def solve(self, page: Any, context: dict) -> bool: ...


class CaptchaResolver:
    """Registry：挑战类型 -> 解法。Outlook 需先 perimeterx 再 arkose，由 flow 步骤依次调用。"""

    def __init__(self):
        self._solvers: dict[str, CaptchaService] = {}

    def register(self, solver: CaptchaService) -> None:
        self._solvers[solver.kind] = solver

    async def solve(self, kind: str, page: Any, context: dict) -> bool:
        return await self._solvers[kind].solve(page, context)


class EmailPoolService(ABC):
    @abstractmethod
    def acquire(self) -> EmailAccount | None: ...
    @abstractmethod
    def add(self, account: EmailAccount) -> None: ...


class SmsService(ABC):
    @abstractmethod
    async def get_number(self, *, country: str) -> str: ...
    @abstractmethod
    async def get_code(self, number: str) -> str: ...
    @abstractmethod
    async def release(self, number: str) -> None: ...


class TokenExtractor(ABC):
    @abstractmethod
    async def extract(self, page: Any, account: EmailAccount) -> dict: ...
```

`services/worker/capabilities/__init__.py`：
```python
from worker.capabilities.interfaces import (
    BrowserSession, EmailAccount,
    BrowserService, ProxyService, CaptchaService, CaptchaResolver,
    EmailPoolService, SmsService, TokenExtractor,
)

__all__ = [
    "BrowserSession", "EmailAccount",
    "BrowserService", "ProxyService", "CaptchaService", "CaptchaResolver",
    "EmailPoolService", "SmsService", "TokenExtractor",
]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd services && python -m pytest tests/worker/test_capabilities_interfaces.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add services/worker/capabilities/interfaces.py services/worker/capabilities/__init__.py services/tests/worker/test_capabilities_interfaces.py
git commit -m "feat(worker): capabilities/interfaces.py —— 7个共享能力ABC+值对象+CaptchaResolver"
```

---

## Task 3: capabilities/bundle.py —— ServiceBundle 依赖注入容器

**Files:**
- Create: `services/worker/capabilities/bundle.py`
- Modify: `services/worker/capabilities/__init__.py`（追加 re-export ServiceBundle）
- Test: `services/tests/worker/test_bundle.py`

- [ ] **Step 1: 写失败测试**

`services/tests/worker/test_bundle.py`：
```python
from worker.capabilities.bundle import ServiceBundle


def test_bundle_all_optional_defaults_none():
    b = ServiceBundle()
    assert b.browser is None and b.proxy is None and b.captcha is None
    assert b.emails is None and b.sms is None and b.tokens is None and b.accounts is None


def test_bundle_holds_injected():
    sentinel = object()
    b = ServiceBundle(browser=sentinel)
    assert b.browser is sentinel
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services && python -m pytest tests/worker/test_bundle.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 bundle.py**

`services/worker/capabilities/bundle.py`：
```python
"""ServiceBundle：共享能力的依赖注入容器。本里程碑各平台仍走 bridge，故全字段可选。"""

from dataclasses import dataclass
from typing import Any

from worker.capabilities.interfaces import (
    BrowserService, ProxyService, CaptchaResolver,
    EmailPoolService, SmsService, TokenExtractor,
)


@dataclass
class ServiceBundle:
    browser: BrowserService | None = None
    proxy: ProxyService | None = None
    captcha: CaptchaResolver | None = None
    emails: EmailPoolService | None = None
    sms: SmsService | None = None
    tokens: TokenExtractor | None = None
    accounts: Any | None = None   # AccountRepository（现成于 account_service，后续注入）
```

`services/worker/capabilities/__init__.py` 追加：
```python
from worker.capabilities.bundle import ServiceBundle
```
并把 `"ServiceBundle"` 加入 `__all__`。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd services && python -m pytest tests/worker/test_bundle.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add services/worker/capabilities/bundle.py services/worker/capabilities/__init__.py services/tests/worker/test_bundle.py
git commit -m "feat(worker): capabilities/bundle.py —— ServiceBundle 依赖注入容器"
```

---

## Task 4: flows/outlook.py —— Outlook flow 转 LegacyBridgeStep（模板范例）

**Files:**
- Create: `services/worker/flows/outlook.py`
- Create: `services/tests/worker/test_outlook_flow.py`
- Delete: `services/tests/worker/test_step_engine_mode.py`（被新测试取代）

**搬迁来源：** `services/worker/step_engine.py` 的 `OutlookRegistrationFlow.execute_step`（72-136）两个分支——"Generate credentials"(74-87)、"Browser registration with proxy"(89-131)。把每个分支体原样搬进对应的 `async def _step_*(self, context, services) -> StepResult` 方法（把 `step_number=step_number, name=step_name` 这类参数去掉，改为 `StepResult(success=..., data=...)`；`run()` 会回填 step_number/name）。

- [ ] **Step 1: 写失败测试**

`services/tests/worker/test_outlook_flow.py`（移植自 test_step_engine_mode.py，改测 `_step_register`）：
```python
import asyncio
import sys
import types
from worker.flows.outlook import OutlookRegistrationFlow


def _make_flow():
    return OutlookRegistrationFlow.__new__(OutlookRegistrationFlow)  # 绕过 __init__(LegacyBridge)


def _fake_module(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


def test_get_steps_are_legacy_kind():
    flow = _make_flow()
    steps = flow.get_steps()
    assert [s.name for s in steps] == ["Generate credentials", "Browser registration with proxy"]
    assert all(s.kind == "legacy" for s in steps)


def test_mode_hybrid_dispatches(monkeypatch):
    called = {}
    async def fake_hybrid(proxy_str, idx):
        called["mode"] = "hybrid"; return ("h@outlook.com", "Pw!", "rt")
    monkeypatch.setitem(sys.modules, "outlook_hybrid",
                        _fake_module("outlook_hybrid", register_outlook_hybrid=fake_hybrid))
    flow = _make_flow()
    ctx = {"mode": "hybrid", "proxy": "p", "idx": 0}
    res = asyncio.run(flow._step_register(ctx, None))
    assert called["mode"] == "hybrid" and res.success is True
    assert ctx["email"] == "h@outlook.com" and ctx["refresh_token"] == "rt"


def test_mode_protocol_dispatches(monkeypatch):
    called = {}
    def fake_protocol(proxy_str=None, idx=0):
        called["mode"] = "protocol"; return ("p@outlook.com", "Pw!")
    monkeypatch.setitem(sys.modules, "register_outlook_standalone",
                        _fake_module("register_outlook_standalone", register_outlook_protocol=fake_protocol))
    flow = _make_flow()
    ctx = {"mode": "protocol", "proxy": "p", "idx": 0}
    res = asyncio.run(flow._step_register(ctx, None))
    assert called["mode"] == "protocol" and res.success is True and ctx["email"] == "p@outlook.com"


def test_default_mode_is_browser(monkeypatch):
    called = {}
    async def fake_browser(bb, idx, proxy_str):
        called["mode"] = "browser"; return ("b@outlook.com", "Pw!", None)
    monkeypatch.setitem(sys.modules, "register_outlook_standalone",
                        _fake_module("register_outlook_standalone", _register_one_browser=fake_browser))
    common_pkg = _fake_module("common"); common_pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "common", common_pkg)
    monkeypatch.setitem(sys.modules, "common.browser_provider",
                        _fake_module("common.browser_provider", get_browser_provider=lambda: object()))
    flow = _make_flow()
    ctx = {"proxy": "p", "idx": 0}
    res = asyncio.run(flow._step_register(ctx, None))
    assert called["mode"] == "browser" and res.success is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd services && python -m pytest tests/worker/test_outlook_flow.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'worker.flows.outlook'`）

- [ ] **Step 3: 实现 outlook.py**

`services/worker/flows/outlook.py`：
```python
"""Outlook 浏览器注册流程。本里程碑各步骤经 LegacyBridgeStep 调遗留 register_outlook_standalone.py。"""

from worker.flows.base import RegistrationFlow, FlowRegistry, Step, StepResult, LegacyBridgeStep


class OutlookRegistrationFlow(RegistrationFlow):
    def get_steps(self) -> list[Step]:
        return [
            LegacyBridgeStep("Generate credentials", self._step_generate),
            LegacyBridgeStep("Browser registration with proxy", self._step_register),
        ]

    async def _step_generate(self, context: dict, services) -> StepResult:
        from register_outlook_standalone import (
            generate_email_password, generate_birthday, generate_name,
        )
        email, password, _prefix = generate_email_password()
        first, last = generate_name()
        birthday = generate_birthday()
        context["email"] = email
        context["password"] = password
        context["first_name"] = first
        context["last_name"] = last
        context["birthday"] = birthday
        return StepResult(success=True, data={"email": email, "first_name": first, "last_name": last})

    async def _step_register(self, context: dict, services) -> StepResult:
        proxy_str = context.get("proxy", "")
        idx = context.get("idx", 0)
        mode = context.get("mode", "browser")
        email = password = graph_token = None

        if mode == "hybrid":
            from outlook_hybrid import register_outlook_hybrid
            result = await register_outlook_hybrid(proxy_str, idx)
            if result and result[0]:
                email, password = result[0], result[1]
                graph_token = result[2] if len(result) > 2 else None
        elif mode == "protocol":
            from register_outlook_standalone import register_outlook_protocol
            result = register_outlook_protocol(proxy_str, idx)
            if result and result[0]:
                email, password = result[0], result[1]
        else:  # browser（默认）
            from common.browser_provider import get_browser_provider
            from register_outlook_standalone import _register_one_browser
            bb = get_browser_provider()
            result = await _register_one_browser(bb, idx, proxy_str)
            if result and len(result) >= 2 and result[0]:
                email, password = result[0], result[1]
                graph_token = result[2] if len(result) > 2 else None

        if email:
            context["email"] = email
            context["password"] = password
            if graph_token:
                context["refresh_token"] = graph_token
            return StepResult(success=True, data={"email": email, "has_token": bool(graph_token), "mode": mode})

        return StepResult(success=False, error=f"Registration failed (mode={mode}) — check ixBrowser/proxy/captcha")


FlowRegistry.register("outlook", OutlookRegistrationFlow)
```

- [ ] **Step 4: 删除旧测试 + 运行新测试确认通过**

```bash
git rm services/tests/worker/test_step_engine_mode.py
```
Run: `cd services && python -m pytest tests/worker/test_outlook_flow.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add services/worker/flows/outlook.py services/tests/worker/test_outlook_flow.py
git commit -m "refactor(worker): Outlook flow 转 flows/outlook.py(LegacyBridgeStep契约)"
```

---

## Task 5: flows/gmail.py —— Gmail flow 转 LegacyBridgeStep

**Files:**
- Create: `services/worker/flows/gmail.py`
- Test: `services/tests/worker/test_gmail_flow.py`

**搬迁来源：** `step_engine.py` 的 `GmailRegistrationFlow.execute_step`（145-254）。步骤名（来自当前 get_steps）：`"Generate profile"`、`"Browser drive to phone"`、`"Phone verification"`、`"Save and cleanup"`。把每个 `elif step_name == "<名>"` 分支体搬进对应方法 `_step_generate_profile` / `_step_drive_to_phone` / `_step_phone_verify` / `_step_save_cleanup`，签名统一 `async def _x(self, context, services) -> StepResult`，返回值改为 `StepResult(success=..., error=..., data=...)`（去掉 step_number/name 参数）。

- [ ] **Step 1: 写失败测试**

`services/tests/worker/test_gmail_flow.py`：
```python
from worker.flows.gmail import GmailRegistrationFlow


def test_get_steps_names_and_legacy_kind():
    flow = GmailRegistrationFlow.__new__(GmailRegistrationFlow)
    steps = flow.get_steps()
    assert [s.name for s in steps] == [
        "Generate profile", "Browser drive to phone", "Phone verification", "Save and cleanup",
    ]
    assert all(s.kind == "legacy" for s in steps)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services && python -m pytest tests/worker/test_gmail_flow.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'worker.flows.gmail'`）

- [ ] **Step 3: 实现 gmail.py**（完整移植自 step_engine.py 145-253；平台键沿用现有 `"google"`）

`services/worker/flows/gmail.py`：
```python
"""Gmail 混合方案注册流程。本里程碑经 LegacyBridgeStep 调遗留 register_gmail_hybrid.py。
浏览器铸 BotGuard token（姓名→生日→用户名→密码）+ 浏览器手机验证。"""

import asyncio
import random
import string

from worker.flows.base import RegistrationFlow, FlowRegistry, Step, StepResult, LegacyBridgeStep


class GmailRegistrationFlow(RegistrationFlow):
    def get_steps(self) -> list[Step]:
        return [
            LegacyBridgeStep("Generate profile", self._step_generate_profile),
            LegacyBridgeStep("Browser drive to phone", self._step_drive_to_phone),
            LegacyBridgeStep("Phone verification", self._step_phone_verify),
            LegacyBridgeStep("Save and cleanup", self._step_save_cleanup),
        ]

    async def _step_generate_profile(self, context: dict, services) -> StepResult:
        first = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 8))).capitalize()
        last = ''.join(random.choices(string.ascii_lowercase, k=random.randint(5, 8))).capitalize()
        password = f"Gm{''.join(random.choices(string.ascii_letters + string.digits, k=6))}!{random.randint(10, 99)}"
        context["profile"] = {
            "first": first, "last": last, "pw": password,
            "year": random.randint(1988, 1998),
            "month": random.randint(1, 12),
            "day": random.randint(1, 28),
        }
        return StepResult(success=True, data={"first": first, "last": last})

    async def _step_drive_to_phone(self, context: dict, services) -> StepResult:
        from common.browser import open_and_connect
        from register_gmail_hybrid import drive_to_phone, build_signup_url
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            bb, pid, browser, ctx, page = await open_and_connect(
                name=f"gmail_{context.get('profile', {}).get('first', 'unknown')}", p=p,
            )
            context["_bb"] = bb
            context["_pid"] = pid
            context["_page"] = page
            context["_context"] = ctx
            signup_url = build_signup_url()
            await page.goto(signup_url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            profile = context.get("profile", {})
            success = await drive_to_phone(page, profile)
            context["profile"] = profile
            if success:
                return StepResult(success=True, data={"username": profile.get("username", "")})
            return StepResult(success=False, error="Failed to drive to phone verification page")

    async def _step_phone_verify(self, context: dict, services) -> StepResult:
        page = context.get("_page")
        ctx = context.get("_context")
        profile = context.get("profile", {})
        if not page:
            return StepResult(success=False, error="No browser session available")
        from register_gmail_hybrid import browser_phone_and_finalize
        pid = context.get("_pid")
        result = await browser_phone_and_finalize(page, profile, ctx=ctx, profile_id=pid)
        if result and result.get("email"):
            context["email"] = result["email"]
            context["password"] = profile.get("pw", "")
            context["result"] = result
            return StepResult(success=True, data={"email": result["email"]})
        return StepResult(success=False, error=f"Phone verification failed: {result}")

    async def _step_save_cleanup(self, context: dict, services) -> StepResult:
        bb = context.pop("_bb", None)
        pid = context.pop("_pid", None)
        context.pop("_page", None)
        context.pop("_context", None)
        if bb and pid:
            from common.browser import teardown
            await teardown(bb, pid, delete=True)
        return StepResult(success=True, data={
            "email": context.get("email"),
            "password": context.get("password"),
            "username": context.get("profile", {}).get("username"),
        })


FlowRegistry.register("google", GmailRegistrationFlow)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd services && python -m pytest tests/worker/test_gmail_flow.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add services/worker/flows/gmail.py services/tests/worker/test_gmail_flow.py
git commit -m "refactor(worker): Gmail flow 转 flows/gmail.py(LegacyBridgeStep契约)"
```

---

## 通用搬迁程序（Tasks 6-8 实现步骤，确定性、无新逻辑）

Tasks 6-8 是把 `step_engine.py` 中对应 flow 的 `execute_step` 分支**机械搬迁**到独立文件（已有 Outlook/Gmail 两个完整范例）。每个文件按此程序生成：

1. 文件头：`from worker.flows.base import RegistrationFlow, FlowRegistry, Step, StepResult, LegacyBridgeStep`，并补上该 flow `execute_step` 体内用到的 stdlib import（`random`/`string`/`asyncio` 等，按需）。
2. 定义 `class <Flow>(RegistrationFlow)`，`get_steps()` 返回该 flow 各步骤名的 `LegacyBridgeStep("<步骤名>", self._step_<x>)` 列表（步骤名/顺序见各 Task 的映射表）。
3. 每个 `_step_<x>(self, context: dict, services) -> StepResult`：方法体 = `step_engine.py` 中对应 `if/elif step_name == "<步骤名>":` 的分支体，**原样粘贴**。
4. 把分支体内每个 `return StepResult(step_number=step_number, name=step_name, success=Y, error=Z, data=W)` 改为 `return StepResult(success=Y, error=Z, data=W)`（删去 `step_number`/`name`——`run()` 回填）。
5. **丢弃**原 `execute_step` 末尾的 `return StepResult(... "Unknown step: ..." ...)` 兜底分支。
6. 文件底：`FlowRegistry.register("<平台键>", <Flow>)`。

> 该转换不引入任何新逻辑，仅相对 Outlook/Gmail 范例替换"类名/步骤名→方法名/源行号/平台键"。各 Task 给出这些具体参数。

---

## Task 6: flows/claude.py —— Claude flow 转 LegacyBridgeStep

**Files:**
- Create: `services/worker/flows/claude.py`
- Test: `services/tests/worker/test_claude_flow.py`

**搬迁来源：** `step_engine.py` `ClaudeRegistrationFlow.execute_step`（259-323）。步骤名：`"Prepare email"`、`"Browser login and magic link"`、`"Phone verification"`、`"Extract session and cleanup"` → 方法 `_step_prepare_email` / `_step_login_magic` / `_step_phone_verify` / `_step_extract_session`。平台键 `"claude"`。

- [ ] **Step 1: 写失败测试** — `services/tests/worker/test_claude_flow.py`：
```python
from worker.flows.claude import ClaudeRegistrationFlow


def test_get_steps_names_and_legacy_kind():
    flow = ClaudeRegistrationFlow.__new__(ClaudeRegistrationFlow)
    steps = flow.get_steps()
    assert [s.name for s in steps] == [
        "Prepare email", "Browser login and magic link", "Phone verification", "Extract session and cleanup",
    ]
    assert all(s.kind == "legacy" for s in steps)
```

- [ ] **Step 2: 运行确认失败** — Run: `cd services && python -m pytest tests/worker/test_claude_flow.py -v` → FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现 claude.py** —— 按「通用搬迁程序」生成。参数：类 `ClaudeRegistrationFlow`，源 `step_engine.py` 259-323，平台键 `"claude"`。步骤名→方法名映射：

| 步骤名 | 方法 |
|---|---|
| `Prepare email` | `_step_prepare_email` |
| `Browser login and magic link` | `_step_login_magic` |
| `Phone verification` | `_step_phone_verify` |
| `Extract session and cleanup` | `_step_extract_session` |

- [ ] **Step 4: 运行确认通过** — Run: `cd services && python -m pytest tests/worker/test_claude_flow.py -v` → PASS

- [ ] **Step 5: 提交**
```bash
git add services/worker/flows/claude.py services/tests/worker/test_claude_flow.py
git commit -m "refactor(worker): Claude flow 转 flows/claude.py(LegacyBridgeStep契约)"
```

---

## Task 7: flows/chatgpt.py —— ChatGPT flow 转 LegacyBridgeStep

**Files:**
- Create: `services/worker/flows/chatgpt.py`
- Test: `services/tests/worker/test_chatgpt_flow.py`

**搬迁来源：** `step_engine.py` `ChatGptRegistrationFlow.execute_step`（328-401）。步骤名：`"Prepare email"`、`"Browser navigate and submit email"`、`"Email verification"`、`"Complete onboarding"`、`"Save cookies and export"` → 方法 `_step_prepare_email` / `_step_navigate_submit` / `_step_email_verify` / `_step_onboarding` / `_step_save_export`。平台键 `"chatgpt"`。

- [ ] **Step 1: 写失败测试** — `services/tests/worker/test_chatgpt_flow.py`：
```python
from worker.flows.chatgpt import ChatGptRegistrationFlow


def test_get_steps_names_and_legacy_kind():
    flow = ChatGptRegistrationFlow.__new__(ChatGptRegistrationFlow)
    steps = flow.get_steps()
    assert [s.name for s in steps] == [
        "Prepare email", "Browser navigate and submit email", "Email verification",
        "Complete onboarding", "Save cookies and export",
    ]
    assert all(s.kind == "legacy" for s in steps)
```

- [ ] **Step 2: 运行确认失败** — Run: `cd services && python -m pytest tests/worker/test_chatgpt_flow.py -v` → FAIL

- [ ] **Step 3: 实现 chatgpt.py** —— 按「通用搬迁程序」生成。参数：类 `ChatGptRegistrationFlow`，源 `step_engine.py` 328-401，平台键 `"chatgpt"`。步骤名→方法名映射：

| 步骤名 | 方法 |
|---|---|
| `Prepare email` | `_step_prepare_email` |
| `Browser navigate and submit email` | `_step_navigate_submit` |
| `Email verification` | `_step_email_verify` |
| `Complete onboarding` | `_step_onboarding` |
| `Save cookies and export` | `_step_save_export` |

- [ ] **Step 4: 运行确认通过** — Run: `cd services && python -m pytest tests/worker/test_chatgpt_flow.py -v` → PASS

- [ ] **Step 5: 提交**
```bash
git add services/worker/flows/chatgpt.py services/tests/worker/test_chatgpt_flow.py
git commit -m "refactor(worker): ChatGPT flow 转 flows/chatgpt.py(LegacyBridgeStep契约)"
```

---

## Task 8: flows/grok.py —— Grok flow 转 LegacyBridgeStep

**Files:**
- Create: `services/worker/flows/grok.py`
- Test: `services/tests/worker/test_grok_flow.py`

**搬迁来源：** `step_engine.py` `GrokRegistrationFlow.execute_step`（406-480）。步骤名：`"Prepare email and proxy"`、`"Browser navigate with Turnstile"`、`"Email verification"`、`"Complete registration"`、`"Save cookies and upload"` → 方法 `_step_prepare` / `_step_navigate_turnstile` / `_step_email_verify` / `_step_complete` / `_step_save_upload`。平台键 `"grok"`。

- [ ] **Step 1: 写失败测试** — `services/tests/worker/test_grok_flow.py`：
```python
from worker.flows.grok import GrokRegistrationFlow


def test_get_steps_names_and_legacy_kind():
    flow = GrokRegistrationFlow.__new__(GrokRegistrationFlow)
    steps = flow.get_steps()
    assert [s.name for s in steps] == [
        "Prepare email and proxy", "Browser navigate with Turnstile", "Email verification",
        "Complete registration", "Save cookies and upload",
    ]
    assert all(s.kind == "legacy" for s in steps)
```

- [ ] **Step 2: 运行确认失败** — Run: `cd services && python -m pytest tests/worker/test_grok_flow.py -v` → FAIL

- [ ] **Step 3: 实现 grok.py** —— 按「通用搬迁程序」生成。参数：类 `GrokRegistrationFlow`，源 `step_engine.py` 406-480，平台键 `"grok"`。步骤名→方法名映射：

| 步骤名 | 方法 |
|---|---|
| `Prepare email and proxy` | `_step_prepare` |
| `Browser navigate with Turnstile` | `_step_navigate_turnstile` |
| `Email verification` | `_step_email_verify` |
| `Complete registration` | `_step_complete` |
| `Save cookies and upload` | `_step_save_upload` |

- [ ] **Step 4: 运行确认通过** — Run: `cd services && python -m pytest tests/worker/test_grok_flow.py -v` → PASS

- [ ] **Step 5: 提交**
```bash
git add services/worker/flows/grok.py services/tests/worker/test_grok_flow.py
git commit -m "refactor(worker): Grok flow 转 flows/grok.py(LegacyBridgeStep契约)"
```

---

## Task 9: flows/__init__.py 注册全平台 + step_engine.py 向后兼容壳

**Files:**
- Modify: `services/worker/flows/__init__.py`
- Modify: `services/worker/step_engine.py`（清空为 re-export 壳）
- Test: `services/tests/worker/test_flow_registry_all.py`

- [ ] **Step 1: 写失败测试**

`services/tests/worker/test_flow_registry_all.py`：
```python
import worker.flows  # 触发各平台注册
from worker.flows import FlowRegistry
from worker.flows.outlook import OutlookRegistrationFlow
# 向后兼容：旧路径仍可用
from worker.step_engine import FlowRegistry as LegacyRegistry, OutlookRegistrationFlow as LegacyOutlook
import pytest


@pytest.mark.parametrize("platform,cls_name", [
    ("outlook", "OutlookRegistrationFlow"),
    ("google", "GmailRegistrationFlow"),
    ("claude", "ClaudeRegistrationFlow"),
    ("chatgpt", "ChatGptRegistrationFlow"),
    ("grok", "GrokRegistrationFlow"),
])
def test_registry_resolves_all_platforms(platform, cls_name):
    flow = FlowRegistry.get(platform)
    assert type(flow).__name__ == cls_name


def test_backcompat_step_engine_reexports():
    assert LegacyRegistry is FlowRegistry
    assert LegacyOutlook is OutlookRegistrationFlow
```

- [ ] **Step 2: 运行确认失败**

Run: `cd services && python -m pytest tests/worker/test_flow_registry_all.py -v`
Expected: FAIL（`google`/`claude` 等未注册 → ValueError；或 step_engine 仍是旧实现，`LegacyRegistry is FlowRegistry` 为 False）

- [ ] **Step 3: 实现**

`services/worker/flows/__init__.py`（追加：import 各平台模块以触发 `FlowRegistry.register`）：
```python
from worker.flows.base import (
    Step, StepFn, StepResult, RegistrationFlow, FlowRegistry, LegacyBridgeStep,
)

# import 各平台模块 → 触发模块底部的 FlowRegistry.register(...)
from worker.flows import outlook, gmail, claude, chatgpt, grok  # noqa: E402,F401

__all__ = ["Step", "StepFn", "StepResult", "RegistrationFlow", "FlowRegistry", "LegacyBridgeStep"]
```

`services/worker/step_engine.py`（**整文件替换**为向后兼容壳）：
```python
"""向后兼容壳：原 step_engine 内容已拆分到 worker.flows。保留此模块供旧 import 路径。"""

from worker.flows import (  # noqa: F401
    Step, StepFn, StepResult, RegistrationFlow, FlowRegistry, LegacyBridgeStep,
)
from worker.flows.outlook import OutlookRegistrationFlow  # noqa: F401
from worker.flows.gmail import GmailRegistrationFlow  # noqa: F401
from worker.flows.claude import ClaudeRegistrationFlow  # noqa: F401
from worker.flows.chatgpt import ChatGptRegistrationFlow  # noqa: F401
from worker.flows.grok import GrokRegistrationFlow  # noqa: F401
```

- [ ] **Step 4: 运行确认通过**

Run: `cd services && python -m pytest tests/worker/test_flow_registry_all.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: 提交**

```bash
git add services/worker/flows/__init__.py services/worker/step_engine.py services/tests/worker/test_flow_registry_all.py
git commit -m "refactor(worker): 全平台注册到 flows/ + step_engine 降为向后兼容壳"
```

---

## Task 10: 全量回归 —— 确认绿色基线

**Files:** 无（验证任务）

- [ ] **Step 1: 跑 worker 全部测试**

Run: `cd services && python -m pytest tests/worker/ -v`
Expected: 全部 PASS（含本里程碑新增 + 原有 worker 测试；`test_step_engine_mode.py` 已被 `test_outlook_flow.py` 取代）

- [ ] **Step 2: 跑 services 全量测试，与基线对比**

Run: `cd services && python -m pytest -q`
Expected: 失败数 ≤ 实施前基线（本里程碑不新增失败）。若有新失败，定位到被改动的 `worker` 模块并修复。

- [ ] **Step 3: 跑 tasks.py 冒烟（import + FlowRegistry 解析，确认 tasks 零改动仍工作）**

Run: `cd services && python -c "from worker.tasks import register_outlook_single; from worker.step_engine import FlowRegistry; print('outlook ->', FlowRegistry.get('outlook').__class__.__name__)"`
Expected: 输出 `outlook -> OutlookRegistrationFlow`，无 ImportError。

- [ ] **Step 4: 提交（若 Step 2 有修复）**

```bash
git add -A
git commit -m "test(worker): 里程碑1 全量回归绿色基线确认"
```

---

## 门后里程碑（不在本计划拆解）

- **里程碑2 — Outlook 原生化**：把 `flows/outlook.py` 各 LegacyBridgeStep 逐个换成调 `capabilities` 原生服务的 native Step（`PerimeterXHoldSolver`(预热+9-12s长按)、`BrowserService`、`ProxyService`、`TokenExtractor`）；落地这些 capabilities 的具体实现。
- **里程碑3 — Gmail 原生化**。
- **里程碑4 — 下游 Claude/ChatGPT/Grok 原生化**。
- **里程碑5 — 退役 + 大扫除**：删 `legacy_bridge`、单体归档 `legacy/`、清 64 垃圾 + `.gitignore`、`_*.py` 移 `research/`、新增 `docs/ARCHITECTURE.md`+`docs/CONVENTIONS.md`。
