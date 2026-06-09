# 现有注册脚本迁移到新架构计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有的 register_outlook_standalone.py (2100行)、register_gmail_hybrid.py (684行)、register_gmail_protocol.py (829行) 和 common/ 模块的核心业务逻辑接入新微服务架构的 step_engine，使注册功能真正可用。

**Architecture:** 采用「适配器包装」而非「重写」策略——现有脚本已经过实战验证，直接重写风险极高。核心思路是将现有函数作为实现细节，包装到新架构的 RegistrationFlow.execute_step() 接口中。common/ 模块中缺失的关键功能（stealth 注入、firefox.fun 适配器、react_fill 工具）提取到 services/shared/ 中复用。

**Tech Stack:** Python 3.11+, Playwright, httpx, 现有 common/ 模块

**关键原则：** 
- 不重写已验证的业务逻辑，只包装适配
- 现有脚本作为「旧引擎」保留，新架构通过 import 调用
- 逐步迁移，每个 Task 独立可测试

---

## 迁移范围

### Phase 1: 通用模块补全（本计划）
将现有 common/ 中新架构缺失的关键模块迁移到 services/shared/

### Phase 2: Outlook 注册接入（单独计划）  
将 register_outlook_standalone.py 的核心函数包装到 OutlookRegistrationFlow

### Phase 3: Gmail 注册接入（单独计划）
将 register_gmail_hybrid.py + register_gmail_protocol.py 包装到 GmailRegistrationFlow

---

## Phase 1 文件结构

```
services/shared/
├── browser_utils/
│   ├── __init__.py
│   ├── stealth.py          — STEALTH_JS 常量 + inject_stealth() 从 common/browser.py 迁移
│   ├── input_helpers.py    — human_type() + react_fill() 从 common/browser.py 迁移
│   └── session.py          — open_and_connect() + teardown() 适配新 BrowserProvider
├── sms_providers/
│   └── firefox_fun.py      — firefox.fun 适配器（你的主用平台，新架构中缺失）
└── captcha/
    ├── __init__.py
    ├── base.py             — CaptchaSolver 抽象基类
    ├── capsolver.py        — CapSolver 集成（Arkose + PerimeterX）
    └── ezcaptcha.py        — EZ-Captcha 集成
```

---

### Task 1: 迁移 Stealth 反检测脚本

**来源:** common/browser.py 第 28-124 行 (STEALTH_JS) + 第 127-142 行 (inject_stealth)

**Files:**
- Create: `services/shared/browser_utils/__init__.py`
- Create: `services/shared/browser_utils/stealth.py`
- Create: `services/tests/shared/test_stealth.py`

- [ ] **Step 1: 写测试**

```python
# services/tests/shared/test_stealth.py
from shared.browser_utils.stealth import STEALTH_JS, StealthInjector


def test_stealth_js_not_empty():
    assert len(STEALTH_JS) > 500


def test_stealth_js_hides_webdriver():
    assert "navigator" in STEALTH_JS
    assert "webdriver" in STEALTH_JS


def test_stealth_js_fakes_chrome():
    assert "window.chrome" in STEALTH_JS


def test_stealth_js_hides_cdp():
    assert "cdc_" in STEALTH_JS


def test_injector_instance():
    injector = StealthInjector()
    assert injector.script == STEALTH_JS
```

- [ ] **Step 2: 从 common/browser.py 提取 STEALTH_JS 和 inject_stealth**

```python
# services/shared/browser_utils/stealth.py
"""反检测 Stealth 脚本。从 common/browser.py 完整迁移。

包含 13 项检测对抗：
1. 隐藏 navigator.webdriver
2. 伪造 chrome 对象
3. 伪造 Permissions API
4. 伪造 plugins/mimeTypes
5. 伪造 languages
6. 伪造 connection.rtt
7. 伪造 hardwareConcurrency/deviceMemory
8. 对抗 PerimeterX CDP 检测
9. 隐藏 Error.stack CDP 痕迹
10. 拦截 defineProperty 注入全局变量
11. 伪造 outerWidth/outerHeight
12. 隐藏 Notification.permission
13. 对抗 iframe contentWindow 检测
"""


# 直接从 common/browser.py 第 28-124 行完整复制
STEALTH_JS = r"""
    // 1. 隐藏 navigator.webdriver
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    try { delete navigator.__proto__.webdriver; } catch(e) {}

    // 2. 伪造 chrome 对象
    if (!window.chrome) {
        window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}, app: {}};
    }

    // 3. 伪造 Permissions API
    const origQuery = window.navigator.permissions?.query;
    if (origQuery) {
        window.navigator.permissions.query = (params) => (
            params.name === 'notifications' ?
                Promise.resolve({state: Notification.permission}) :
                origQuery(params)
        );
    }

    // 4. 伪造 plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format', length: 1},
            {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '', length: 1},
            {name: 'Native Client', filename: 'internal-nacl-plugin', description: '', length: 1},
        ],
    });

    // 5. 伪造 languages
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});

    // 6. 伪造 connection.rtt
    if (navigator.connection) {
        Object.defineProperty(navigator.connection, 'rtt', {get: () => 50});
    }

    // 7. 隐藏 Headless/Automation 相关
    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
    Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

    // 8. 对抗 PerimeterX CDP 检测
    const cdcProps = Object.getOwnPropertyNames(window).filter(p =>
        p.match(/^cdc_|^__cdc|^_cdp|^__cdp|^chrome_devtools/i)
    );
    cdcProps.forEach(p => { try { delete window[p]; } catch(e) {} });

    // 9. 隐藏 Error.stack 中的 CDP 痕迹
    const origPrepare = Error.prepareStackTrace;
    Error.prepareStackTrace = function(err, stack) {
        const filtered = stack.filter(s => {
            const fn = s.getFunctionName() || '';
            const file = s.getFileName() || '';
            return !fn.includes('cdp') && !file.includes('pptr') &&
                   !file.includes('playwright') && !file.includes('puppeteer');
        });
        if (origPrepare) return origPrepare(err, filtered);
        return err + '\n' + filtered.map(s => '    at ' + s).join('\n');
    };

    // 10. 隐藏 Runtime.evaluate 注入的全局变量
    const origDefineProperty = Object.defineProperty;
    Object.defineProperty = function(obj, prop, desc) {
        if (obj === window && typeof prop === 'string' &&
            (prop.startsWith('cdc_') || prop.startsWith('__cdc'))) {
            return obj;
        }
        return origDefineProperty.call(this, obj, prop, desc);
    };

    // 11. 伪造 window.outerWidth/outerHeight
    if (window.outerWidth === 0) {
        Object.defineProperty(window, 'outerWidth', {get: () => window.innerWidth + 16});
    }
    if (window.outerHeight === 0) {
        Object.defineProperty(window, 'outerHeight', {get: () => window.innerHeight + 88});
    }

    // 12. 隐藏 Notification.permission 异常
    if (Notification.permission === 'denied') {
        Object.defineProperty(Notification, 'permission', {get: () => 'default'});
    }

    // 13. 对抗 iframe 检测
    const origGetter = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
    if (origGetter) {
        Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
            get: function() {
                const w = origGetter.get.call(this);
                if (w) {
                    try { Object.defineProperty(w.navigator, 'webdriver', {get: () => undefined}); } catch(e) {}
                }
                return w;
            }
        });
    }
"""


class StealthInjector:
    """Stealth 注入器。负责将反检测脚本注入到浏览器上下文中。"""

    def __init__(self, custom_script: str | None = None):
        self._script = custom_script or STEALTH_JS

    @property
    def script(self) -> str:
        return self._script

    async def inject(self, context, page) -> None:
        """注入反检测脚本（CDP + init_script + evaluate 三重保险）"""
        try:
            cdp = await context.new_cdp_session(page)
            await cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": self._script})
        except Exception:
            pass
        try:
            await page.evaluate(f"() => {{{self._script}}}")
        except Exception:
            pass
        try:
            await context.add_init_script(f"() => {{{self._script}}}")
        except Exception:
            pass
```

```python
# services/shared/browser_utils/__init__.py
from shared.browser_utils.stealth import STEALTH_JS, StealthInjector

__all__ = ["STEALTH_JS", "StealthInjector"]
```

- [ ] **Step 3: 运行测试**

Run: `cd services && python -m pytest tests/shared/test_stealth.py -v`
Expected: 5 passed

- [ ] **Step 4: Commit**

```bash
git add services/shared/browser_utils/ services/tests/shared/test_stealth.py
git commit -m "feat(shared): migrate stealth JS injection from common/browser.py (13 anti-detection measures)"
```

---

### Task 2: 迁移 human_type + react_fill 输入工具

**来源:** common/browser.py 第 219-292 行

**Files:**
- Create: `services/shared/browser_utils/input_helpers.py`
- Create: `services/tests/shared/test_input_helpers.py`

- [ ] **Step 1: 写测试**

```python
# services/tests/shared/test_input_helpers.py
from shared.browser_utils.input_helpers import InputHelper


def test_input_helper_instance():
    helper = InputHelper()
    assert helper is not None


def test_react_fill_js_template():
    helper = InputHelper()
    js = helper.react_fill_js("hello")
    assert "hello" in js
    assert "dispatchEvent" in js
    assert "input" in js
```

- [ ] **Step 2: 实现**

```python
# services/shared/browser_utils/input_helpers.py
"""浏览器输入辅助工具。从 common/browser.py 迁移 human_type + react_fill。"""

import asyncio
import random


class InputHelper:
    """封装浏览器表单输入的常用操作。"""

    @staticmethod
    async def human_type(page, selector: str, text: str, delay_range: tuple = (0.05, 0.18)) -> None:
        """模拟人工逐字输入。"""
        el = page.locator(selector).first
        await el.click()
        for ch in text:
            await el.type(ch, delay=random.uniform(*delay_range) * 1000)
        await asyncio.sleep(random.uniform(0.2, 0.5))

    @staticmethod
    async def react_fill(page, selector: str, text: str, tries: int = 3, delay: int = 55, settle: float = 0.6) -> bool:
        """填写 React 受控输入框，确保框架 state 真正更新。

        React 的坑：page.fill() 只写 DOM .value，不触发合成 onChange。
        解法：1) 键盘逐字输入触发真实事件  2) JS setter 兜底。
        """
        el = page.locator(selector).first
        try:
            if await el.count() == 0:
                return False
        except Exception:
            return False

        async def _readback():
            try:
                return (await el.input_value()).strip()
            except Exception:
                return ""

        for i in range(tries):
            try:
                await el.click(timeout=4000)
                await el.press("Control+A", timeout=2000)
                await el.press("Delete", timeout=2000)
                await page.keyboard.type(text, delay=delay)
            except Exception:
                pass
            await asyncio.sleep(settle)
            if await _readback() == text:
                return True

            try:
                await el.evaluate(
                    """(node, v) => {
                        const proto = node.tagName === 'TEXTAREA'
                            ? window.HTMLTextAreaElement.prototype
                            : window.HTMLInputElement.prototype;
                        const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                        setter.call(node, v);
                        node.dispatchEvent(new Event('input', {bubbles: true}));
                        node.dispatchEvent(new Event('change', {bubbles: true}));
                    }""", text)
            except Exception:
                pass
            await asyncio.sleep(settle)
            if await _readback() == text:
                return True

        return False

    @staticmethod
    def react_fill_js(text: str) -> str:
        """返回 React 受控输入的 JS 注入代码（用于 evaluate）。"""
        return f"""(node) => {{
            const proto = node.tagName === 'TEXTAREA'
                ? window.HTMLTextAreaElement.prototype
                : window.HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
            setter.call(node, {repr(text)});
            node.dispatchEvent(new Event('input', {{bubbles: true}}));
            node.dispatchEvent(new Event('change', {{bubbles: true}}));
        }}"""
```

更新 `__init__.py`:
```python
# services/shared/browser_utils/__init__.py
from shared.browser_utils.stealth import STEALTH_JS, StealthInjector
from shared.browser_utils.input_helpers import InputHelper

__all__ = ["STEALTH_JS", "StealthInjector", "InputHelper"]
```

- [ ] **Step 3: 运行测试**
- [ ] **Step 4: Commit**

---

### Task 3: 添加 firefox.fun SMS 适配器

**来源:** common/sms.py 第 27-97 行 (get_phone/get_code/release)

**Files:**
- Create: `services/sms_service/providers/firefox_fun.py`
- Create: `services/tests/sms_service/test_firefox_fun.py`

- [ ] **Step 1: 写测试**

```python
# services/tests/sms_service/test_firefox_fun.py
from sms_service.providers.base import ProviderRegistry


def test_firefox_fun_registered():
    # 导入触发注册
    import sms_service.providers.firefox_fun  # noqa
    assert ProviderRegistry.is_registered("firefox_fun")


def test_firefox_fun_config_schema():
    import sms_service.providers.firefox_fun  # noqa
    providers = ProviderRegistry.list_providers()
    ff = next(p for p in providers if p["name"] == "firefox_fun")
    assert "token" in ff["config_schema"]
    assert "project_id" in ff["config_schema"]
```

- [ ] **Step 2: 实现适配器**

```python
# services/sms_service/providers/firefox_fun.py
"""firefox.fun 接码平台适配器。从 common/sms.py 迁移核心逻辑。

这是项目的主用接码平台，使用项目号(iid)制度。
API: act=getPhone/getPhoneCode/cancelPhone
响应格式: 管道分隔 1|pkey|...|country_code|...|phone
"""

import asyncio
import re
import httpx

from sms_service.providers.base import (
    SMSProvider,
    ProviderRegistry,
    AcquireResult,
    CodeResult,
    OrderStatus,
)


@ProviderRegistry.register("firefox_fun")
class FirefoxFunProvider(SMSProvider):
    display_name = "Firefox.fun"
    config_schema = {
        "token": {"type": "string", "label": "API Token", "required": True},
        "base_url": {
            "type": "string",
            "label": "API Base URL",
            "default": "http://www.firefox.fun/yhapi.ashx",
        },
        "project_id": {
            "type": "string",
            "label": "项目号 (iid)",
            "required": True,
            "default": "2313",
        },
        "max_price": {
            "type": "string",
            "label": "价格上限",
            "default": "0",
        },
    }

    @property
    def _base_url(self) -> str:
        return self._config.get("base_url", "http://www.firefox.fun/yhapi.ashx")

    @property
    def _token(self) -> str:
        return self._config.get("token", "")

    @property
    def _project_id(self) -> str:
        return self._config.get("project_id", "2313")

    async def get_balance(self) -> float:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self._base_url, params={
                "act": "getBalance", "token": self._token,
            })
            text = resp.text.strip()
            try:
                return float(text)
            except ValueError:
                return 0.0

    async def get_number(self, service: str, country: str) -> AcquireResult:
        max_price = self._config.get("max_price", "0")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(self._base_url, params={
                "act": "getPhone",
                "token": self._token,
                "iid": service or self._project_id,
                "country": country,
                "maxPrice": str(max_price),
                "did": "", "dock": "", "otpmode": "", "mobile": "", "pushUrl": "",
            })
        text = resp.text.strip()
        parts = text.split("|")
        if parts[0] == "1" and len(parts) >= 8:
            pkey = parts[1]
            country_code = parts[4]
            phone = parts[7]
            return AcquireResult(
                order_id=pkey,
                phone_number=f"+{country_code}{phone}",
                provider=self.name,
            )
        raise ValueError(f"firefox.fun get_number failed: {text}")

    async def get_code(self, order_id: str, timeout: int = 180) -> CodeResult:
        elapsed = 0
        interval = 5
        while elapsed < timeout:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(self._base_url, params={
                    "act": "getPhoneCode", "token": self._token, "pkey": order_id,
                })
            text = resp.text.strip()
            parts = text.split("|")
            if parts[0] == "1" and len(parts) >= 2:
                code = parts[1]
                return CodeResult(order_id=order_id, code=code, status=OrderStatus.RECEIVED)
            await asyncio.sleep(interval)
            elapsed += interval
        return CodeResult(order_id=order_id, code=None, status=OrderStatus.TIMEOUT)

    async def complete(self, order_id: str) -> None:
        pass

    async def cancel(self, order_id: str) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.get(self._base_url, params={
                "act": "cancelPhone", "token": self._token, "pkey": order_id,
            })
```

更新 `providers/__init__.py` 添加 import:
```python
from sms_service.providers.firefox_fun import FirefoxFunProvider
```

- [ ] **Step 3: 运行测试**
- [ ] **Step 4: Commit**

---

### Task 4: 创建验证码 Solver 框架

**来源:** register_outlook_standalone.py 中的 5 个 solver 函数

**Files:**
- Create: `services/shared/captcha/__init__.py`
- Create: `services/shared/captcha/base.py`
- Create: `services/shared/captcha/capsolver.py`
- Create: `services/shared/captcha/ezcaptcha.py`
- Create: `services/tests/shared/test_captcha.py`

- [ ] **Step 1: 写测试**

```python
# services/tests/shared/test_captcha.py
from shared.captcha.base import CaptchaSolver, CaptchaType
from shared.captcha.capsolver import CapSolverClient
from shared.captcha.ezcaptcha import EzCaptchaClient


def test_captcha_types():
    assert CaptchaType.ARKOSE.value == "arkose"
    assert CaptchaType.RECAPTCHA.value == "recaptcha"
    assert CaptchaType.PERIMETERX.value == "perimeterx"


def test_capsolver_init():
    solver = CapSolverClient(api_key="test-key")
    assert solver.name == "capsolver"


def test_ezcaptcha_init():
    solver = EzCaptchaClient(api_key="test-key")
    assert solver.name == "ezcaptcha"


def test_solver_registry():
    from shared.captcha import SOLVER_REGISTRY
    assert "capsolver" in SOLVER_REGISTRY
    assert "ezcaptcha" in SOLVER_REGISTRY
```

- [ ] **Step 2: 实现 CaptchaSolver 基类**

```python
# services/shared/captcha/base.py
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass
from typing import Any


class CaptchaType(Enum):
    ARKOSE = "arkose"
    RECAPTCHA = "recaptcha"
    PERIMETERX = "perimeterx"
    HCAPTCHA = "hcaptcha"


@dataclass
class CaptchaResult:
    success: bool
    token: str = ""
    error: str = ""


class CaptchaSolver(ABC):
    """验证码求解器抽象基类。策略模式。"""

    name: str = ""

    def __init__(self, api_key: str, **kwargs):
        self._api_key = api_key
        self._extra = kwargs

    @abstractmethod
    async def solve_arkose(self, public_key: str, page_url: str, **kwargs) -> CaptchaResult:
        ...

    @abstractmethod
    async def solve_recaptcha(self, site_key: str, page_url: str, **kwargs) -> CaptchaResult:
        ...

    async def solve_perimeterx(self, page_url: str, **kwargs) -> CaptchaResult:
        return CaptchaResult(success=False, error="Not supported")
```

- [ ] **Step 3: 实现 CapSolver 集成**

```python
# services/shared/captcha/capsolver.py
"""CapSolver 验证码打码平台集成。
从 register_outlook_standalone.py 的 solve_arkose_capsolver() 和 solve_perimeterx_capsolver() 迁移。
"""

import asyncio
import httpx

from shared.captcha.base import CaptchaSolver, CaptchaResult


class CapSolverClient(CaptchaSolver):
    name = "capsolver"

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        self._base_url = kwargs.get("base_url", "https://api.capsolver.com")

    async def solve_arkose(self, public_key: str, page_url: str, **kwargs) -> CaptchaResult:
        max_wait = kwargs.get("max_wait", 120)
        payload = {
            "clientKey": self._api_key,
            "task": {
                "type": "FunCaptchaTaskProxyLess",
                "websitePublicKey": public_key,
                "websiteURL": page_url,
            },
        }
        return await self._submit_and_poll(payload, max_wait)

    async def solve_recaptcha(self, site_key: str, page_url: str, **kwargs) -> CaptchaResult:
        max_wait = kwargs.get("max_wait", 120)
        payload = {
            "clientKey": self._api_key,
            "task": {
                "type": "ReCaptchaV2TaskProxyLess",
                "websiteKey": site_key,
                "websiteURL": page_url,
            },
        }
        return await self._submit_and_poll(payload, max_wait)

    async def solve_perimeterx(self, page_url: str, **kwargs) -> CaptchaResult:
        max_wait = kwargs.get("max_wait", 120)
        payload = {
            "clientKey": self._api_key,
            "task": {
                "type": "AntiPerimeterXTask",
                "websiteURL": page_url,
            },
        }
        return await self._submit_and_poll(payload, max_wait)

    async def _submit_and_poll(self, payload: dict, max_wait: int) -> CaptchaResult:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self._base_url}/createTask", json=payload)
            data = resp.json()
            if data.get("errorId", 1) != 0:
                return CaptchaResult(success=False, error=data.get("errorDescription", "Unknown"))
            task_id = data.get("taskId")
            if not task_id:
                return CaptchaResult(success=False, error="No task ID")

            elapsed = 0
            while elapsed < max_wait:
                await asyncio.sleep(3)
                elapsed += 3
                resp = await client.post(f"{self._base_url}/getTaskResult", json={
                    "clientKey": self._api_key, "taskId": task_id,
                })
                result = resp.json()
                status = result.get("status", "")
                if status == "ready":
                    token = result.get("solution", {}).get("token", "")
                    return CaptchaResult(success=True, token=token)
                if status == "failed":
                    return CaptchaResult(success=False, error=result.get("errorDescription", ""))

        return CaptchaResult(success=False, error="Timeout")
```

- [ ] **Step 4: 实现 EZ-Captcha 集成**

```python
# services/shared/captcha/ezcaptcha.py
"""EZ-Captcha 验证码打码平台集成。
从 register_outlook_standalone.py 的 solve_funcaptcha_ezcaptcha() 迁移。
"""

import asyncio
import httpx

from shared.captcha.base import CaptchaSolver, CaptchaResult


class EzCaptchaClient(CaptchaSolver):
    name = "ezcaptcha"

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        self._base_url = kwargs.get("base_url", "https://api.ez-captcha.com")

    async def solve_arkose(self, public_key: str, page_url: str, **kwargs) -> CaptchaResult:
        max_wait = kwargs.get("max_wait", 120)
        payload = {
            "clientKey": self._api_key,
            "task": {
                "type": "FunCaptchaTaskProxyLess",
                "websitePublicKey": public_key,
                "websiteURL": page_url,
            },
        }
        return await self._submit_and_poll(payload, max_wait)

    async def solve_recaptcha(self, site_key: str, page_url: str, **kwargs) -> CaptchaResult:
        max_wait = kwargs.get("max_wait", 120)
        payload = {
            "clientKey": self._api_key,
            "task": {
                "type": "ReCaptchaV2TaskProxyLess",
                "websiteKey": site_key,
                "websiteURL": page_url,
            },
        }
        return await self._submit_and_poll(payload, max_wait)

    async def _submit_and_poll(self, payload: dict, max_wait: int) -> CaptchaResult:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self._base_url}/createTask", json=payload)
            data = resp.json()
            if data.get("errorId", 1) != 0:
                return CaptchaResult(success=False, error=data.get("errorDescription", "Unknown"))
            task_id = data.get("taskId")
            if not task_id:
                return CaptchaResult(success=False, error="No task ID")

            elapsed = 0
            while elapsed < max_wait:
                await asyncio.sleep(5)
                elapsed += 5
                resp = await client.post(f"{self._base_url}/getTaskResult", json={
                    "clientKey": self._api_key, "taskId": task_id,
                })
                result = resp.json()
                status = result.get("status", "")
                if status == "ready":
                    token = result.get("solution", {}).get("token", "")
                    return CaptchaResult(success=True, token=token)
                if status == "failed":
                    return CaptchaResult(success=False, error=result.get("errorDescription", ""))

        return CaptchaResult(success=False, error="Timeout")
```

```python
# services/shared/captcha/__init__.py
from shared.captcha.base import CaptchaSolver, CaptchaType, CaptchaResult
from shared.captcha.capsolver import CapSolverClient
from shared.captcha.ezcaptcha import EzCaptchaClient

SOLVER_REGISTRY: dict[str, type[CaptchaSolver]] = {
    "capsolver": CapSolverClient,
    "ezcaptcha": EzCaptchaClient,
}

__all__ = [
    "CaptchaSolver", "CaptchaType", "CaptchaResult",
    "CapSolverClient", "EzCaptchaClient", "SOLVER_REGISTRY",
]
```

- [ ] **Step 5: 运行全部测试**
- [ ] **Step 6: Commit**

---

### Task 5: 创建 Legacy 适配桥

**Purpose:** 让新架构的 step_engine 能直接 import 和调用现有根目录下的脚本函数，无需复制代码。

**Files:**
- Create: `services/worker/legacy_bridge.py`
- Create: `services/tests/worker/test_legacy_bridge.py`

- [ ] **Step 1: 写测试**

```python
# services/tests/worker/test_legacy_bridge.py
import os
import sys
from worker.legacy_bridge import LegacyBridge


def test_legacy_bridge_resolves_root():
    bridge = LegacyBridge()
    root = bridge.project_root
    assert os.path.isdir(root)


def test_legacy_path_added_to_sys():
    bridge = LegacyBridge()
    bridge.ensure_importable()
    assert bridge.project_root in sys.path
```

- [ ] **Step 2: 实现**

```python
# services/worker/legacy_bridge.py
"""Legacy 适配桥。让 worker 中的新代码能 import 根目录下的旧脚本。

使用方式:
    from worker.legacy_bridge import LegacyBridge
    bridge = LegacyBridge()
    bridge.ensure_importable()
    # 现在可以 import 旧模块
    from common.browser import open_and_connect, teardown, inject_stealth
    from common.sms import get_phone, get_code, release
"""

import os
import sys


class LegacyBridge:
    """将项目根目录加入 sys.path，使旧脚本可被新架构 import。"""

    def __init__(self):
        self._root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)
        )))

    @property
    def project_root(self) -> str:
        return self._root

    def ensure_importable(self) -> None:
        if self._root not in sys.path:
            sys.path.insert(0, self._root)

    def get_config(self, key: str, default: str = "") -> str:
        self.ensure_importable()
        try:
            import config as legacy_config
            return getattr(legacy_config, key, default)
        except ImportError:
            return default
```

- [ ] **Step 3: 运行测试**
- [ ] **Step 4: Commit**

---

## Phase 2 & 3 方向说明

Phase 1 完成后，Outlook 和 Gmail 的迁移思路是：

### OutlookRegistrationFlow (Phase 2)

```python
# services/worker/step_engine.py 中 OutlookRegistrationFlow.execute_step 的目标状态：

async def execute_step(self, step_number: int, step_name: str, context: dict) -> StepResult:
    bridge = LegacyBridge()
    bridge.ensure_importable()
    
    if step_name == "Create email":
        # 直接调用现有函数生成邮箱
        from register_outlook_standalone import generate_email_password
        email, password = generate_email_password()
        context["email"] = email
        context["password"] = password
        return StepResult(...)

    elif step_name == "Fill form + Captcha":
        # 合并表单填充和验证码为一步（现有脚本中它们紧密耦合）
        from common.browser import open_and_connect, teardown, inject_stealth
        from register_outlook_standalone import register_outlook
        bb, pid, browser, ctx, page = await open_and_connect(...)
        result = await register_outlook(page, ctx, ...)
        ...
```

### GmailRegistrationFlow (Phase 3)

```python
async def execute_step(self, step_number: int, step_name: str, context: dict) -> StepResult:
    bridge = LegacyBridge()
    bridge.ensure_importable()
    
    if step_name == "Browser drive to phone":
        # 直接调用现有的 drive_to_phone
        from register_gmail_hybrid import drive_to_phone
        success = await drive_to_phone(page, profile)
        ...
    
    elif step_name == "Phone verification":
        from register_gmail_hybrid import browser_phone_and_finalize
        result = await browser_phone_and_finalize(page, profile, ...)
        ...
```

**关键决策：现有脚本保持原样，新架构通过 LegacyBridge import 调用。** 这样：
- 零风险：已验证的业务逻辑不被修改
- 渐进式：未来可以逐步将函数从旧脚本移到新模块
- 可回退：随时可以退回到直接运行旧脚本
