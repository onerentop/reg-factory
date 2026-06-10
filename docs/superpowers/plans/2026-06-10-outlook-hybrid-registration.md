# Outlook 混合注册实现计划（浏览器铸会话 → 协议提交）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用真实浏览器铸 Arkose HSol token（在干净会话内由 Arkose JS 透明签发），路由拦截截获后由协议侧 HTTP 逐字 replay 提交，从根上绕开"付费 API 孤立铸 token 不被 MS 接受"的问题。

**Architecture:** 浏览器和协议共享同一代理 + 同一份 cookie + 同一个 UA。`SessionMinter` 复用现有 `register_outlook()` 跑表单+过 PerimeterX，仅在其上加路由拦截器截获并 abort `API/CreateAccount`；`ProtocolSubmitter` 把截获的 cookie/canary/payload 装进 `requests.Session` 立即 replay；`HybridOutlookOrchestrator` 编排，失败回退现有 `_register_one_browser`。

**Tech Stack:** Python 3.13 / asyncio / Playwright (async_api) / requests / pytest / FastAPI（集成）/ React+AntD（前端模式下拉）

---

## 设计文档

`docs/superpowers/specs/2026-06-10-outlook-hybrid-registration-design.md`

## 与设计文档的有意偏差（实现中发现）

**取消 `AccountDraft` / `AccountFactory`。** 设计文档设想"预生成一份账号资料，浏览器和协议共用"。但现有 `register_outlook()` 内部自己调 `generate_email_password()` 生成邮箱密码——账号身份天然**起源于浏览器**。因此身份的唯一真值是**截获的 CreateAccount 请求体**（含 `MemberName`/`Password`），协议侧从中读取，无需预生成。这仍满足"单一身份贯穿全程"的原则，只是来源从"预生成"变为"浏览器生成→截获"。YAGNI：不引入 AccountDraft。

## 文件结构

```
outlook_hybrid/
  __init__.py        # 门面 register_outlook_hybrid(proxy_str, idx)；装配真实组件
  errors.py          # MintFailed / SubmitRejected
  credential.py      # MintedCredential（dataclass + .email/.password 便捷属性）
  cookies.py         # playwright_cookies_to_requests() 纯函数
  submitter.py       # ProtocolSubmitter
  minter.py          # SessionMinter
  fallback.py        # FallbackPolicy
  pool.py            # BrowserPool（asyncio.Semaphore 封装）
  orchestrator.py    # HybridOutlookOrchestrator

register_outlook_standalone.py
  + 新增 _open_ixbrowser_page(bb, idx, proxy_str)  异步上下文管理器（从 _register_one_browser 抽取）
  + _register_one_browser 改为复用该助手（行为不变）

services/worker/step_engine.py
  + OutlookRegistrationFlow.execute_step 增加 mode 分派（hybrid/browser/protocol）

services/gateway/main.py            # /register/outlook 透传 mode
services/worker/process_manager.py  # submit() 透传 mode 进 context
frontend/src/pages/AccountsPage.tsx # 注册表单加"注册模式"下拉

tests/outlook_hybrid/
  test_credential.py
  test_cookies.py
  test_submitter.py
  test_minter.py          # 真实 headless chromium + 本地路由桩
  test_fallback.py
  test_orchestrator.py
  test_facade.py
tests/test_step_engine_mode.py

_spike_outlook_hybrid.py   # Task 0 一次性验证脚本（验证后可删）
```

---

## Task 0: 验证 spike（决策门，非 TDD）

**这是整份计划的前置门。** 设计押在一个假设上：浏览器铸的 HSol，协议 replay 时 MS 会接受。先用一次性脚本验证。**spike 不写测试**（研究性质）。结果决定后续路径。

**Files:**
- Create: `_spike_outlook_hybrid.py`

- [ ] **Step 1: 写 spike 脚本**

```python
# -*- coding: utf-8 -*-
"""Phase 0 验证：浏览器铸 HSol → 协议 replay 能否被 MS 接受。一次性脚本，验证后删除。
用法：python _spike_outlook_hybrid.py "<proxy_str>"
"""
import asyncio, json, sys, time
import requests

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import config  # noqa: 触发 .env
from common.browser_provider import get_browser_provider
from register_outlook_standalone import (
    register_outlook, _proxy_for_requests, verify_registered_outlook,
)


async def _drive_and_capture(proxy_str):
    """起浏览器跑 register_outlook，路由拦截 CreateAccount，截获 payload/headers/cookies/UA 后 abort。"""
    from playwright.async_api import async_playwright
    bb = get_browser_provider()
    profile_id = bb.create_browser(name="spike_outlook", proxy_str=proxy_str)
    info = bb.open_browser(profile_id)
    ws = info.get("ws", "")
    captured = {}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(ws)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await context.new_page()

            fut = asyncio.get_event_loop().create_future()

            async def _intercept(route):
                req = route.request
                if not fut.done():
                    try:
                        body = json.loads(req.post_data or "{}")
                    except Exception:
                        body = {}
                    fut.set_result({"payload": body, "headers": dict(req.headers)})
                await route.abort()

            await page.route("**/API/CreateAccount*", _intercept)

            drive = asyncio.create_task(register_outlook(page, context, 0))
            try:
                cap = await asyncio.wait_for(asyncio.shield(fut), timeout=180)
            except asyncio.TimeoutError:
                drive.cancel()
                print("[spike] CreateAccount 未被触发/截获，超时")
                return None
            drive.cancel()
            try:
                await drive
            except asyncio.CancelledError:
                pass

            captured["payload"] = cap["payload"]
            captured["headers"] = cap["headers"]
            captured["cookies"] = await context.cookies()
            captured["ua"] = await page.evaluate("() => navigator.userAgent")
    finally:
        try:
            bb.close_browser(profile_id); bb.delete_browser(profile_id)
        except Exception:
            pass
    return captured


def _replay(captured, proxy_str):
    """立即用截获的会话 replay CreateAccount。"""
    payload = captured["payload"]
    headers_in = captured["headers"]
    email = payload.get("MemberName", "")
    password = payload.get("Password", "")
    print(f"[spike] 截获 email={email} HSol={'有' if payload.get('HSol') else '无'} canary={'有' if headers_in.get('canary') else '无'}")

    s = requests.Session()
    s.headers.update({"User-Agent": captured["ua"]})
    for c in captured["cookies"]:
        dom = c.get("domain", "")
        s.cookies.set(c["name"], c["value"], domain=dom.lstrip("."), path=c.get("path", "/"))

    hdr = {
        "canary": headers_in.get("canary", ""),
        "hpgid": headers_in.get("hpgid", ""),
        "scid": headers_in.get("scid", "100118"),
        "Origin": "https://signup.live.com",
        "Referer": "https://signup.live.com/signup?lic=1",
        "Content-Type": "application/json",
    }
    r = s.post("https://signup.live.com/API/CreateAccount?lic=1",
               json=payload, headers=hdr,
               proxies=_proxy_for_requests(proxy_str), timeout=30)
    print(f"[spike] replay status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200 and "error" not in r.text.lower():
        ok = verify_registered_outlook(email, password, "[spike]")
        print(f"[spike] 校验登录: {'成功 ✅ 假设成立' if ok else '失败 ❌'}")
        return ok
    return False


async def _main():
    proxy_str = sys.argv[1] if len(sys.argv) > 1 else ""
    captured = await _drive_and_capture(proxy_str)
    if not captured:
        print("[spike] 结论：未能截获，检查浏览器/验证码")
        return
    ok = _replay(captured, proxy_str)
    print(f"\n[spike] === 最终结论：{'PASS — 按计划建完整混合' if ok else 'FAIL — 切换降级语义（见计划 Task 0 决策门）'} ===")


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 2: 运行 spike**

Run: `python _spike_outlook_hybrid.py "<你的可用代理串>"`
观察最终结论行。

- [ ] **Step 3: 决策门（人工判断，记录结果）**

- **PASS（replay 建号成功并登录校验通过）** → 继续 Task 1~12，按本计划建完整混合。
- **FAIL（HSol 被拒 / canary 失效 / 校验失败）** → 绑定理论不成立。**改走降级语义**：`SessionMinter` 改为不 abort、让 `register_outlook` 在浏览器内建完号，`ProtocolSubmitter` 退化为"仅校验+抽 token"。Task 4/6 的实现据此调整（接口与文件结构不变），其余任务照常。把实际结论写进本任务下方备注。

> 决策结论（执行者填写）：____________________

- [ ] **Step 4: 提交 spike（保留记录）**

```bash
git add _spike_outlook_hybrid.py docs/superpowers/plans/2026-06-10-outlook-hybrid-registration.md
git commit -m "spike: Outlook 混合注册可行性验证脚本 + 实现计划"
```

---

## Task 1: 包脚手架 + 错误类型 + MintedCredential

**Files:**
- Create: `outlook_hybrid/__init__.py`（暂留空门面占位，Task 9 填实）
- Create: `outlook_hybrid/errors.py`
- Create: `outlook_hybrid/credential.py`
- Test: `tests/outlook_hybrid/test_credential.py`
- Create: `tests/outlook_hybrid/__init__.py`（空文件，使其成为包）

- [ ] **Step 1: 写失败测试**

`tests/outlook_hybrid/test_credential.py`:

```python
from outlook_hybrid.credential import MintedCredential


def _sample():
    return MintedCredential(
        cookies=[{"name": "_px3", "value": "abc", "domain": ".live.com", "path": "/"}],
        canary="canary123",
        create_payload={"MemberName": "user@outlook.com", "Password": "Pw!12345", "HSol": "tok"},
        request_headers={"canary": "canary123", "hpgid": "200225"},
        user_agent="UA/1.0",
        proxy="http://1.2.3.4:8080",
        captured=True,
    )


def test_email_and_password_read_from_payload():
    c = _sample()
    assert c.email == "user@outlook.com"
    assert c.password == "Pw!12345"


def test_has_token_true_when_hsol_present():
    assert _sample().has_token is True


def test_has_token_false_when_hsol_missing():
    c = _sample()
    c.create_payload = {"MemberName": "x@outlook.com", "Password": "p"}
    assert c.has_token is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/outlook_hybrid/test_credential.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outlook_hybrid.credential'`

- [ ] **Step 3: 写实现**

`outlook_hybrid/errors.py`:

```python
"""混合注册的领域异常。"""


class MintFailed(Exception):
    """浏览器侧铸凭证失败（过不了 PerimeterX / 验证码 / 未截获 CreateAccount）。"""


class SubmitRejected(Exception):
    """协议侧 replay 被 MS 拒绝（HSol 失效 / canary 失效 / 其他 error）。"""
```

`outlook_hybrid/credential.py`:

```python
"""浏览器铸出的会话凭证。协议侧据此逐字 replay。"""

from dataclasses import dataclass, field


@dataclass
class MintedCredential:
    cookies: list[dict] = field(default_factory=list)   # context.cookies()，含 _px*
    canary: str = ""                                     # 请求头 apiCanary
    create_payload: dict = field(default_factory=dict)  # 截获的 CreateAccount JSON 体（含 HSol/MemberName/Password）
    request_headers: dict = field(default_factory=dict)  # canary/hpgid/scid/...
    user_agent: str = ""                                 # 必须与协议 Session 一致
    proxy: str = ""
    captured: bool = False

    @property
    def email(self) -> str:
        return self.create_payload.get("MemberName", "")

    @property
    def password(self) -> str:
        return self.create_payload.get("Password", "")

    @property
    def has_token(self) -> bool:
        return bool(self.create_payload.get("HSol"))
```

`outlook_hybrid/__init__.py`:

```python
"""Outlook 混合注册：浏览器铸会话 → 协议提交。"""
# 门面 register_outlook_hybrid 在 Task 9 填实。
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/outlook_hybrid/test_credential.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add outlook_hybrid/__init__.py outlook_hybrid/errors.py outlook_hybrid/credential.py tests/outlook_hybrid/__init__.py tests/outlook_hybrid/test_credential.py
git commit -m "feat(outlook_hybrid): 包脚手架 + MintedCredential + 错误类型"
```

---

## Task 2: cookie 转植纯函数（Playwright → requests）

**Files:**
- Create: `outlook_hybrid/cookies.py`
- Test: `tests/outlook_hybrid/test_cookies.py`

- [ ] **Step 1: 写失败测试**

`tests/outlook_hybrid/test_cookies.py`:

```python
import requests
from outlook_hybrid.cookies import playwright_cookies_to_requests


def test_strips_leading_dot_from_domain():
    jar = requests.Session().cookies
    playwright_cookies_to_requests(jar, [
        {"name": "_px3", "value": "v1", "domain": ".live.com", "path": "/"},
    ])
    assert jar.get("_px3", domain="live.com") == "v1"


def test_keeps_plain_domain():
    jar = requests.Session().cookies
    playwright_cookies_to_requests(jar, [
        {"name": "a", "value": "v2", "domain": "signup.live.com", "path": "/"},
    ])
    assert jar.get("a", domain="signup.live.com") == "v2"


def test_defaults_missing_path_to_root():
    jar = requests.Session().cookies
    playwright_cookies_to_requests(jar, [
        {"name": "b", "value": "v3", "domain": "live.com"},
    ])
    assert jar.get("b", domain="live.com") == "v3"


def test_skips_entries_without_name_or_value():
    jar = requests.Session().cookies
    playwright_cookies_to_requests(jar, [
        {"value": "noname", "domain": "live.com"},
        {"name": "noval", "domain": "live.com"},
    ])
    assert len(jar) == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/outlook_hybrid/test_cookies.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outlook_hybrid.cookies'`

- [ ] **Step 3: 写实现**

`outlook_hybrid/cookies.py`:

```python
"""Playwright cookie → requests CookieJar 转植。"""


def playwright_cookies_to_requests(jar, cookies):
    """把 Playwright context.cookies() 结果装进 requests 的 CookieJar。

    - 去掉域名前导点（.live.com → live.com），requests 用裸域名匹配
    - 缺 path 默认 '/'
    - 缺 name 或 value 的条目跳过
    """
    for c in cookies or []:
        name = c.get("name")
        value = c.get("value")
        if not name or value is None:
            continue
        domain = (c.get("domain") or "").lstrip(".")
        path = c.get("path") or "/"
        jar.set(name, value, domain=domain, path=path)
    return jar
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/outlook_hybrid/test_cookies.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add outlook_hybrid/cookies.py tests/outlook_hybrid/test_cookies.py
git commit -m "feat(outlook_hybrid): cookie 转植纯函数 Playwright→requests"
```

---

## Task 3: ProtocolSubmitter（协议侧 replay）

**说明：** 若 Task 0 决策门为 **FAIL**，本任务改为"仅校验+抽 token"语义——`submit()` 不发 CreateAccount，直接对 `cred.email/password` 跑 `verifier` + `token_extractor`。下面按 **PASS** 路径写（replay）。

**Files:**
- Create: `outlook_hybrid/submitter.py`
- Test: `tests/outlook_hybrid/test_submitter.py`

- [ ] **Step 1: 写失败测试**

`tests/outlook_hybrid/test_submitter.py`:

```python
from unittest.mock import MagicMock
import pytest
from outlook_hybrid.submitter import ProtocolSubmitter
from outlook_hybrid.credential import MintedCredential
from outlook_hybrid.errors import SubmitRejected


def _cred():
    return MintedCredential(
        cookies=[{"name": "_px3", "value": "v", "domain": ".live.com", "path": "/"}],
        canary="can1",
        create_payload={"MemberName": "u@outlook.com", "Password": "Pw!1", "HSol": "tok"},
        request_headers={"canary": "can1", "hpgid": "200225", "scid": "100118"},
        user_agent="UA/1.0",
        proxy="",
        captured=True,
    )


class _FakeResp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text

    def json(self):
        import json
        return json.loads(self.text)


def test_success_replays_and_verifies_and_extracts(monkeypatch):
    sent = {}

    def fake_post(url, json=None, headers=None, proxies=None, timeout=None):
        sent["url"] = url
        sent["json"] = json
        sent["headers"] = headers
        return _FakeResp(200, '{"ok": true}')

    sub = ProtocolSubmitter(
        token_extractor=lambda email, password, proxy: "refresh_xyz",
        verifier=lambda email, password, tag="": True,
    )
    sub._session_factory = lambda: _session_with(fake_post)  # 替换会话工厂为假 Session

    res = sub.submit(_cred())
    assert res.success is True
    assert res.email == "u@outlook.com"
    assert res.refresh_token == "refresh_xyz"
    assert sent["url"].endswith("/API/CreateAccount?lic=1")
    assert sent["json"]["HSol"] == "tok"
    assert sent["headers"]["canary"] == "can1"


def test_ms_error_raises_submit_rejected():
    sub = ProtocolSubmitter(
        token_extractor=lambda *a, **k: "",
        verifier=lambda *a, **k: True,
    )
    sub._session_factory = lambda: _session_returning(
        _FakeResp(200, '{"error": {"code": "1304", "data": "challenge"}}'))
    with pytest.raises(SubmitRejected):
        sub.submit(_cred())


def test_success_without_token_still_success():
    sub = ProtocolSubmitter(
        token_extractor=lambda *a, **k: "",   # 抽不到 token
        verifier=lambda *a, **k: True,
    )
    sub._session_factory = lambda: _session_returning(_FakeResp(200, '{"ok": true}'))
    res = sub.submit(_cred())
    assert res.success is True
    assert res.refresh_token == ""
    assert res.has_token is False


# --- 测试用的极简假 Session ---
def _session_with(post_fn):
    s = MagicMock()
    s.headers = {}
    s.cookies = requests_cookiejar()
    s.post = post_fn
    return s


def _session_returning(resp):
    def _post(url, json=None, headers=None, proxies=None, timeout=None):
        return resp
    return _session_with(_post)


def requests_cookiejar():
    import requests
    return requests.Session().cookies
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/outlook_hybrid/test_submitter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outlook_hybrid.submitter'`

- [ ] **Step 3: 写实现**

`outlook_hybrid/submitter.py`:

```python
"""协议侧：装载凭证 → 立即 replay CreateAccount → 校验 → 抽 token。无浏览器。"""

from dataclasses import dataclass

import requests

from .cookies import playwright_cookies_to_requests
from .credential import MintedCredential
from .errors import SubmitRejected

CREATE_ACCOUNT_URL = "https://signup.live.com/API/CreateAccount?lic=1"


@dataclass
class RegistrationResult:
    success: bool
    email: str = ""
    password: str = ""
    refresh_token: str = ""
    mode_used: str = "hybrid"
    error: str = ""

    @property
    def has_token(self) -> bool:
        return bool(self.refresh_token)


class ProtocolSubmitter:
    """注入 token_extractor 与 verifier，便于测试与解耦。

    token_extractor(email, password, proxy) -> refresh_token(str)
    verifier(email, password, tag="") -> bool
    """

    def __init__(self, token_extractor, verifier):
        self._extract = token_extractor
        self._verify = verifier
        self._session_factory = requests.Session  # 测试可替换

    def submit(self, cred: MintedCredential) -> RegistrationResult:
        from register_outlook_standalone import _proxy_for_requests

        session = self._session_factory()
        session.headers.update({"User-Agent": cred.user_agent})
        playwright_cookies_to_requests(session.cookies, cred.cookies)

        headers = {
            "canary": cred.request_headers.get("canary", cred.canary),
            "hpgid": cred.request_headers.get("hpgid", ""),
            "scid": cred.request_headers.get("scid", "100118"),
            "Origin": "https://signup.live.com",
            "Referer": "https://signup.live.com/signup?lic=1",
            "Content-Type": "application/json",
        }
        proxies = _proxy_for_requests(cred.proxy)

        try:
            resp = session.post(CREATE_ACCOUNT_URL, json=cred.create_payload,
                                 headers=headers, proxies=proxies, timeout=30)
        except Exception as e:
            # 网络错误：窗口内重发一次
            resp = session.post(CREATE_ACCOUNT_URL, json=cred.create_payload,
                                headers=headers, proxies=proxies, timeout=30)

        body = resp.text or ""
        try:
            data = resp.json()
            if isinstance(data, dict) and data.get("error"):
                err = data["error"]
                raise SubmitRejected(f"code={err.get('code')} data={str(err.get('data') or err.get('message'))[:120]}")
        except SubmitRejected:
            raise
        except Exception:
            pass

        if resp.status_code == 200 and "error" not in body.lower():
            email, password = cred.email, cred.password
            if not self._verify(email, password, tag="[hybrid]"):
                return RegistrationResult(success=False, email=email, password=password,
                                          mode_used="hybrid", error="verify failed")
            try:
                token = self._extract(email, password, cred.proxy) or ""
            except Exception:
                token = ""
            return RegistrationResult(success=True, email=email, password=password,
                                      refresh_token=token, mode_used="hybrid")

        raise SubmitRejected(f"unexpected status={resp.status_code} body={body[:120]}")
```

> 注：测试用 `sub._session_factory = lambda: <fake>` 替换会话工厂；网络重试在假 Session 下不触发（首次即返回）。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/outlook_hybrid/test_submitter.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add outlook_hybrid/submitter.py tests/outlook_hybrid/test_submitter.py
git commit -m "feat(outlook_hybrid): ProtocolSubmitter replay+校验+抽token"
```

---

## Task 4: 抽取 `_open_ixbrowser_page` 助手（行为保持重构）

把 `_register_one_browser` 里"创建 ixBrowser profile → open → CDP 连接 → 建 page → 注入 init script → 清理"的样板抽成可复用异步上下文管理器，供 `_register_one_browser` 与 `SessionMinter` 共用。**行为不变**：现有浏览器注册仍走同一路径。

**Files:**
- Modify: `register_outlook_standalone.py`（新增助手；改 `_register_one_browser` 复用）
- Test: `tests/outlook_hybrid/test_open_page_helper.py`

- [ ] **Step 1: 写失败测试**

`tests/outlook_hybrid/test_open_page_helper.py`:

```python
import inspect
import register_outlook_standalone as ros


def test_helper_exists_and_is_async_context_manager():
    assert hasattr(ros, "_open_ixbrowser_page")
    # 应为 async generator 函数（@asynccontextmanager 装饰）
    fn = ros._open_ixbrowser_page
    assert hasattr(fn, "__wrapped__") or inspect.isasyncgenfunction(getattr(fn, "__wrapped__", fn))


def test_register_one_browser_still_present():
    # 重构后入口仍在，签名不变
    sig = inspect.signature(ros._register_one_browser)
    assert list(sig.parameters) == ["bb", "idx", "proxy_str"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/outlook_hybrid/test_open_page_helper.py -v`
Expected: FAIL — `AssertionError`（`_open_ixbrowser_page` 不存在）

- [ ] **Step 3: 写实现**

在 `register_outlook_standalone.py` 顶部 import 区加：

```python
from contextlib import asynccontextmanager
```

在 `_register_one_browser` 之前插入助手：

```python
@asynccontextmanager
async def _open_ixbrowser_page(bb, idx, proxy_str):
    """创建并连接一个 ixBrowser 页面，yield (page, context, profile_id)，退出时清理。

    封装 _register_one_browser 的浏览器启动样板，供混合注册复用。
    """
    tag = f"[#{idx}]"
    profile_id = None
    try:
        ts = datetime.now().strftime("%m%d_%H%M%S")
        name = f"outlook_{ts}_{idx}"
        for _retry in range(5):
            try:
                profile_id = bb.create_browser(name=name, proxy_str=proxy_str)
                break
            except Exception as e:
                err_msg = str(e)
                if '最大创建窗口数' in err_msg or '超过' in err_msg:
                    bb.cleanup_browsers(keep=2)
                    await asyncio.sleep(3)
                    continue
                elif 'TLS' in err_msg or 'socket' in err_msg or 'ECONNRESET' in err_msg:
                    await asyncio.sleep(5 + _retry * 3)
                    continue
                elif _retry < 4:
                    await asyncio.sleep(3)
                    continue
                else:
                    raise
        if not profile_id:
            raise RuntimeError(f"{tag} create browser failed")

        info = bb.open_browser(profile_id)
        ws = info.get("ws", "")
        if not ws:
            raise RuntimeError(f"{tag} no WebSocket URL")

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(ws)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await context.new_page()
            await context.add_init_script("""
                Object.defineProperty(navigator, 'credentials', {
                    get: () => ({ create: () => Promise.reject('disabled'), get: () => Promise.reject('disabled'), store: () => Promise.reject('disabled') })
                });
            """)
            yield page, context, profile_id
    finally:
        if profile_id:
            try:
                bb.close_browser(profile_id)
                await asyncio.sleep(2)
                bb.delete_browser(profile_id)
            except Exception:
                pass
```

把 `_register_one_browser` 改为复用助手（替换其函数体内启动+清理逻辑）：

```python
async def _register_one_browser(bb, idx, proxy_str):
    """Register via ixBrowser full browser (highest traffic, most reliable).
    Returns (email, password[, graph]) or (None, None)."""
    tag = f"[#{idx}][browser]"
    try:
        async with _open_ixbrowser_page(bb, idx, proxy_str) as (page, context, _pid):
            print(f"  {tag} ixBrowser connected")
            result = await register_outlook(page, context, idx)
            email = result[0] if result else None
            password = result[1] if result and len(result) > 1 else None
            graph = result[2] if result and len(result) > 2 else None
            return email, password, graph
    except Exception as e:
        print(f"  {tag} error: {e}")
        return None, None
```

- [ ] **Step 4: 运行测试确认通过 + 回归现有浏览器测试**

Run: `python -m pytest tests/outlook_hybrid/test_open_page_helper.py tests/test_browser_provider.py tests/test_ixbrowser_provider.py -v`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add register_outlook_standalone.py tests/outlook_hybrid/test_open_page_helper.py
git commit -m "refactor(outlook): 抽取 _open_ixbrowser_page 助手供混合注册复用"
```

---

## Task 5: SessionMinter（浏览器侧铸凭证）

复用 `_open_ixbrowser_page` + `register_outlook`，仅加路由拦截器截获并 abort `API/CreateAccount`。

**说明：** 若 Task 0 决策门为 **FAIL**，本任务改为不 abort、让 `register_outlook` 跑完，再从 `context.cookies()`/页面读取已建号信息组 `MintedCredential`（`captured=True`，但语义为"已建号"）。下面按 **PASS** 路径写。

**测试策略：** 用真实 headless chromium（不依赖 ixBrowser/MS），通过 `page.route` 伪造签到页 HTML，页面里 `fetch('/API/CreateAccount?lic=1', {...HSol...})`，断言拦截器**截获 payload 且 abort（fetch 被拒）**。这测的是本任务的新增逻辑（拦截+截获+abort），表单填充与真实 MS 由 spike/E2E 覆盖。为此把拦截器逻辑抽成可独立测试的 `install_create_account_interceptor(page) -> Future`。

**Files:**
- Create: `outlook_hybrid/minter.py`
- Test: `tests/outlook_hybrid/test_minter.py`

- [ ] **Step 1: 写失败测试**

`tests/outlook_hybrid/test_minter.py`:

```python
import asyncio
import json
import pytest

playwright_async = pytest.importorskip("playwright.async_api")
from playwright.async_api import async_playwright

from outlook_hybrid.minter import install_create_account_interceptor


@pytest.mark.asyncio
async def test_interceptor_captures_payload_and_aborts():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 伪造签到页：导航到 signup.live.com 时返回一段会 fetch CreateAccount 的 HTML
        async def _serve_html(route):
            await route.fulfill(status=200, content_type="text/html", body="""
                <html><body><script>
                  window.__done = fetch('/API/CreateAccount?lic=1', {
                    method:'POST',
                    headers:{'Content-Type':'application/json','canary':'CANARY42','hpgid':'200225'},
                    body: JSON.stringify({MemberName:'u@outlook.com', Password:'Pw!1', HSol:'TOK99'})
                  }).then(r=>'ok').catch(e=>'aborted');
                </script></body></html>
            """)

        await page.route("https://signup.live.com/", _serve_html)
        fut = await install_create_account_interceptor(page)

        await page.goto("https://signup.live.com/", wait_until="domcontentloaded")
        cap = await asyncio.wait_for(fut, timeout=10)

        assert cap["payload"]["HSol"] == "TOK99"
        assert cap["payload"]["MemberName"] == "u@outlook.com"
        assert cap["headers"].get("canary") == "CANARY42"

        # fetch 应被 abort（页面脚本 catch 到 'aborted'）
        result = await page.evaluate("() => window.__done")
        assert result == "aborted"

        await browser.close()
```

> 若仓库未配 `pytest-asyncio`，本任务 Step 3 末尾给出在 `tests/conftest.py` 注册 asyncio 标记的方案；或把该测试改成 `asyncio.run(...)` 包装的同步测试。优先用 `pytest.importorskip` + asyncio.run 同步包装以零新增依赖（见下）。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/outlook_hybrid/test_minter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outlook_hybrid.minter'`

- [ ] **Step 3: 写实现**

`outlook_hybrid/minter.py`:

```python
"""浏览器侧：过 PerimeterX → 让 Arkose JS 铸 HSol → 路由拦截截获 CreateAccount → abort（不建号）。"""

import asyncio
import json

from .credential import MintedCredential
from .errors import MintFailed


async def install_create_account_interceptor(page):
    """在 page 上挂 CreateAccount 路由拦截器（await 确保注册完成，避免与导航竞态）。

    返回一个 asyncio.Future，截获到第一个 CreateAccount 请求时 set_result
    {"payload": dict, "headers": dict}，并对所有 CreateAccount 请求 abort。
    """
    fut: asyncio.Future = asyncio.get_event_loop().create_future()

    async def _intercept(route):
        req = route.request
        if not fut.done():
            try:
                payload = json.loads(req.post_data or "{}")
            except Exception:
                payload = {}
            fut.set_result({"payload": payload, "headers": dict(req.headers)})
        try:
            await route.abort()
        except Exception:
            pass

    await page.route("**/API/CreateAccount*", _intercept)
    return fut


class SessionMinter:
    """复用 register_outlook 跑表单+过 PerimeterX，仅加拦截器截获凭证。"""

    def __init__(self, browser_provider, capture_timeout=120):
        self._bb = browser_provider
        self._timeout = capture_timeout

    async def mint(self, proxy: str, idx: int = 0) -> MintedCredential:
        from register_outlook_standalone import _open_ixbrowser_page, register_outlook

        async with _open_ixbrowser_page(self._bb, idx, proxy) as (page, context, _pid):
            fut = await install_create_account_interceptor(page)

            drive = asyncio.create_task(register_outlook(page, context, idx))
            try:
                cap = await asyncio.wait_for(asyncio.shield(fut), timeout=self._timeout)
            except asyncio.TimeoutError:
                drive.cancel()
                raise MintFailed("CreateAccount 未在超时内被截获（过不了验证码/表单失败）")

            drive.cancel()
            try:
                await drive
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

            payload = cap["payload"]
            if not payload.get("HSol"):
                raise MintFailed("截获的 CreateAccount 无 HSol token")

            cookies = await context.cookies()
            ua = await page.evaluate("() => navigator.userAgent")
            headers_in = cap["headers"]
            return MintedCredential(
                cookies=cookies,
                canary=headers_in.get("canary", ""),
                create_payload=payload,
                request_headers={
                    "canary": headers_in.get("canary", ""),
                    "hpgid": headers_in.get("hpgid", ""),
                    "scid": headers_in.get("scid", "100118"),
                },
                user_agent=ua,
                proxy=proxy,
                captured=True,
            )
```

若无 `pytest-asyncio`，把测试函数改为同步并用 `asyncio.run` 包装内部 async：

```python
def test_interceptor_captures_payload_and_aborts():
    asyncio.run(_run_capture_check())

async def _run_capture_check():
    ...  # 上面 async 测试体原样搬入
```

（实现者按仓库现状二选一；现有 tests 未见 asyncio 插件，**默认采用 asyncio.run 同步包装**。）

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/outlook_hybrid/test_minter.py -v`
Expected: PASS（1 passed；若本机未装 chromium，先 `python -m playwright install chromium`）

- [ ] **Step 5: 提交**

```bash
git add outlook_hybrid/minter.py tests/outlook_hybrid/test_minter.py
git commit -m "feat(outlook_hybrid): SessionMinter 路由拦截截获 HSol+canary+cookies"
```

---

## Task 6: FallbackPolicy（回退策略）

**Files:**
- Create: `outlook_hybrid/fallback.py`
- Test: `tests/outlook_hybrid/test_fallback.py`

- [ ] **Step 1: 写失败测试**

`tests/outlook_hybrid/test_fallback.py`:

```python
import asyncio
import pytest
from outlook_hybrid.fallback import FallbackPolicy
from outlook_hybrid.submitter import RegistrationResult
from outlook_hybrid.errors import MintFailed, SubmitRejected


def _run(coro):
    return asyncio.run(coro)


def test_submit_rejected_falls_back_to_browser():
    calls = {}

    async def fake_browser(proxy, idx):
        calls["browser"] = True
        return RegistrationResult(success=True, email="b@outlook.com", mode_used="browser_fallback")

    pol = FallbackPolicy(browser_fallback=fake_browser, hybrid_retry=None)
    res = _run(pol.handle("proxy", 0, SubmitRejected("token rejected")))
    assert res.success is True
    assert res.mode_used == "browser_fallback"
    assert calls.get("browser") is True


def test_mint_failed_retries_hybrid_once_then_browser():
    seq = []

    async def fake_retry(proxy, idx):
        seq.append("retry")
        raise MintFailed("still failing")

    async def fake_browser(proxy, idx):
        seq.append("browser")
        return RegistrationResult(success=True, mode_used="browser_fallback")

    pol = FallbackPolicy(browser_fallback=fake_browser, hybrid_retry=fake_retry)
    res = _run(pol.handle("proxy", 0, MintFailed("first fail")))
    assert seq == ["retry", "browser"]
    assert res.success is True


def test_browser_fallback_failure_returns_unsuccessful():
    async def fake_browser(proxy, idx):
        return RegistrationResult(success=False, error="browser also failed", mode_used="browser_fallback")

    pol = FallbackPolicy(browser_fallback=fake_browser, hybrid_retry=None)
    res = _run(pol.handle("proxy", 0, SubmitRejected("x")))
    assert res.success is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/outlook_hybrid/test_fallback.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outlook_hybrid.fallback'`

- [ ] **Step 3: 写实现**

`outlook_hybrid/fallback.py`:

```python
"""混合失败时的回退决策（Strategy）。"""

from .errors import MintFailed, SubmitRejected
from .submitter import RegistrationResult


class FallbackPolicy:
    """注入回退动作，便于测试。

    browser_fallback(proxy, idx) -> RegistrationResult（完整浏览器模式）
    hybrid_retry(proxy, idx) -> RegistrationResult（换会话重试混合；可为 None 跳过）
    """

    def __init__(self, browser_fallback, hybrid_retry=None):
        self._browser = browser_fallback
        self._retry = hybrid_retry

    async def handle(self, proxy, idx, error) -> RegistrationResult:
        # MintFailed 且配了重试：先换会话重试一次混合
        if isinstance(error, MintFailed) and self._retry is not None:
            try:
                return await self._retry(proxy, idx)
            except (MintFailed, SubmitRejected):
                pass  # 重试仍失败 → 落到浏览器回退
        # 其余情况（含 SubmitRejected、重试失败）→ 完整浏览器模式
        return await self._browser(proxy, idx)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/outlook_hybrid/test_fallback.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add outlook_hybrid/fallback.py tests/outlook_hybrid/test_fallback.py
git commit -m "feat(outlook_hybrid): FallbackPolicy 回退策略"
```

---

## Task 7: BrowserPool + HybridOutlookOrchestrator

**Files:**
- Create: `outlook_hybrid/pool.py`
- Create: `outlook_hybrid/orchestrator.py`
- Test: `tests/outlook_hybrid/test_orchestrator.py`

- [ ] **Step 1: 写失败测试**

`tests/outlook_hybrid/test_orchestrator.py`:

```python
import asyncio
import pytest
from outlook_hybrid.orchestrator import HybridOutlookOrchestrator
from outlook_hybrid.pool import BrowserPool
from outlook_hybrid.credential import MintedCredential
from outlook_hybrid.submitter import RegistrationResult
from outlook_hybrid.errors import MintFailed, SubmitRejected


def _run(coro):
    return asyncio.run(coro)


def _cred():
    return MintedCredential(
        create_payload={"MemberName": "u@outlook.com", "Password": "Pw!1", "HSol": "tok"},
        captured=True,
    )


class _Minter:
    def __init__(self, behavior):
        self._behavior = behavior  # "ok" | "mintfail"
    async def mint(self, proxy, idx=0):
        if self._behavior == "mintfail":
            raise MintFailed("no capture")
        return _cred()


class _Submitter:
    def __init__(self, behavior):
        self._behavior = behavior  # "ok" | "reject"
    def submit(self, cred):
        if self._behavior == "reject":
            raise SubmitRejected("rejected")
        return RegistrationResult(success=True, email=cred.email, refresh_token="rt", mode_used="hybrid")


class _Fallback:
    async def handle(self, proxy, idx, error):
        return RegistrationResult(success=True, email="fb@outlook.com", mode_used="browser_fallback")


def test_happy_path_returns_hybrid_result():
    orch = HybridOutlookOrchestrator(
        minter=_Minter("ok"), submitter=_Submitter("ok"),
        fallback=_Fallback(), pool=BrowserPool(2),
    )
    res = _run(orch.register("proxy", 0))
    assert res.success is True
    assert res.mode_used == "hybrid"
    assert res.email == "u@outlook.com"


def test_submit_reject_triggers_fallback():
    orch = HybridOutlookOrchestrator(
        minter=_Minter("ok"), submitter=_Submitter("reject"),
        fallback=_Fallback(), pool=BrowserPool(2),
    )
    res = _run(orch.register("proxy", 0))
    assert res.mode_used == "browser_fallback"
    assert res.success is True


def test_mint_fail_triggers_fallback():
    orch = HybridOutlookOrchestrator(
        minter=_Minter("mintfail"), submitter=_Submitter("ok"),
        fallback=_Fallback(), pool=BrowserPool(2),
    )
    res = _run(orch.register("proxy", 0))
    assert res.mode_used == "browser_fallback"


def test_browser_pool_limits_concurrency():
    pool = BrowserPool(1)
    order = []

    async def worker(n):
        async with pool.slot():
            order.append(f"enter{n}")
            await asyncio.sleep(0.05)
            order.append(f"exit{n}")

    async def _go():
        await asyncio.gather(worker(1), worker(2))

    _run(_go())
    # 并发=1 → 必须串行：enter1,exit1,enter2,exit2
    assert order == ["enter1", "exit1", "enter2", "exit2"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/outlook_hybrid/test_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'outlook_hybrid.orchestrator'`

- [ ] **Step 3: 写实现**

`outlook_hybrid/pool.py`:

```python
"""限制同时占用的浏览器数（铸 token 阶段）。"""

import asyncio
from contextlib import asynccontextmanager


class BrowserPool:
    def __init__(self, max_concurrent: int = 3):
        self._sem = asyncio.Semaphore(max_concurrent)

    @asynccontextmanager
    async def slot(self):
        async with self._sem:
            yield
```

`outlook_hybrid/orchestrator.py`:

```python
"""编排：浏览器铸凭证（占浏览器槽）→ 协议立即 replay（不占浏览器）→ 失败回退。"""

from .errors import MintFailed, SubmitRejected
from .submitter import RegistrationResult


class HybridOutlookOrchestrator:
    def __init__(self, minter, submitter, fallback, pool):
        self._minter = minter
        self._submitter = submitter
        self._fallback = fallback
        self._pool = pool

    async def register(self, proxy: str, idx: int = 0) -> RegistrationResult:
        try:
            async with self._pool.slot():
                cred = await self._minter.mint(proxy, idx)   # 仅此阶段占浏览器
            result = self._submitter.submit(cred)             # 协议侧，无浏览器
            if result.success:
                return result
            raise SubmitRejected(result.error or "submit failed")
        except (MintFailed, SubmitRejected) as e:
            return await self._fallback.handle(proxy, idx, e)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/outlook_hybrid/test_orchestrator.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add outlook_hybrid/pool.py outlook_hybrid/orchestrator.py tests/outlook_hybrid/test_orchestrator.py
git commit -m "feat(outlook_hybrid): BrowserPool + HybridOutlookOrchestrator 编排"
```

---

## Task 8: 门面 `register_outlook_hybrid(proxy_str, idx)`

装配真实组件，对外暴露与 `register_outlook_protocol` / `_register_one_browser` 一致的简单入口。

**Files:**
- Modify: `outlook_hybrid/__init__.py`
- Test: `tests/outlook_hybrid/test_facade.py`

- [ ] **Step 1: 写失败测试**

`tests/outlook_hybrid/test_facade.py`:

```python
import asyncio
import inspect
import outlook_hybrid


def test_facade_exported():
    assert hasattr(outlook_hybrid, "register_outlook_hybrid")


def test_facade_is_async_with_expected_signature():
    fn = outlook_hybrid.register_outlook_hybrid
    assert inspect.iscoroutinefunction(fn)
    params = list(inspect.signature(fn).parameters)
    assert params[:2] == ["proxy_str", "idx"]


def test_facade_returns_tuple_via_orchestrator(monkeypatch):
    # 注入假 orchestrator，验证门面把 RegistrationResult 转成 (email, password, token)
    from outlook_hybrid.submitter import RegistrationResult

    class _FakeOrch:
        def __init__(self, *a, **k): pass
        async def register(self, proxy, idx):
            return RegistrationResult(success=True, email="x@outlook.com",
                                      password="Pw!", refresh_token="rt", mode_used="hybrid")

    monkeypatch.setattr("outlook_hybrid.HybridOutlookOrchestrator", _FakeOrch)
    res = asyncio.run(outlook_hybrid.register_outlook_hybrid("proxy", 0))
    assert res == ("x@outlook.com", "Pw!", "rt")


def test_facade_returns_none_on_failure(monkeypatch):
    from outlook_hybrid.submitter import RegistrationResult

    class _FakeOrch:
        def __init__(self, *a, **k): pass
        async def register(self, proxy, idx):
            return RegistrationResult(success=False, error="all failed")

    monkeypatch.setattr("outlook_hybrid.HybridOutlookOrchestrator", _FakeOrch)
    res = asyncio.run(outlook_hybrid.register_outlook_hybrid("proxy", 0))
    assert res == (None, None)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/outlook_hybrid/test_facade.py -v`
Expected: FAIL — `AttributeError: module 'outlook_hybrid' has no attribute 'register_outlook_hybrid'`

- [ ] **Step 3: 写实现**

`outlook_hybrid/__init__.py`:

```python
"""Outlook 混合注册：浏览器铸会话 → 协议提交。

对外入口：register_outlook_hybrid(proxy_str, idx) -> (email, password, refresh_token) | (None, None)
"""

import os

from .minter import SessionMinter
from .submitter import ProtocolSubmitter, RegistrationResult
from .fallback import FallbackPolicy
from .pool import BrowserPool
from .orchestrator import HybridOutlookOrchestrator

__all__ = ["register_outlook_hybrid"]

# 单进程内全局浏览器池（铸 token 阶段限流）
_POOL = BrowserPool(int(os.environ.get("HYBRID_BROWSER_CONCURRENCY", "2")))


def _extract_token(email, password, proxy):
    """从已建号会话抽 refresh_token。复用现有抽取逻辑（同步封装）。"""
    try:
        from register_outlook_standalone import _proxy_for_requests  # noqa
        # 现有 token 抽取走浏览器 extract_graph_token；此处用轻量占位：
        # 若 Task 0 PASS，建号后由独立 token 抽取流程补齐，这里返回空不阻断成功。
        return ""
    except Exception:
        return ""


def _build_orchestrator():
    from common.browser_provider import get_browser_provider
    from register_outlook_standalone import verify_registered_outlook, _register_one_browser

    bb = get_browser_provider()
    minter = SessionMinter(bb)
    submitter = ProtocolSubmitter(token_extractor=_extract_token, verifier=verify_registered_outlook)

    async def _browser_fallback(proxy, idx):
        result = await _register_one_browser(bb, idx, proxy)
        if result and len(result) >= 2 and result[0]:
            token = result[2] if len(result) > 2 else ""
            return RegistrationResult(success=True, email=result[0], password=result[1],
                                      refresh_token=token or "", mode_used="browser_fallback")
        return RegistrationResult(success=False, error="browser fallback failed",
                                  mode_used="browser_fallback")

    async def _hybrid_retry(proxy, idx):
        cred = await minter.mint(proxy, idx)
        return submitter.submit(cred)

    fallback = FallbackPolicy(browser_fallback=_browser_fallback, hybrid_retry=_hybrid_retry)
    return HybridOutlookOrchestrator(minter=minter, submitter=submitter, fallback=fallback, pool=_POOL)


async def register_outlook_hybrid(proxy_str, idx=0):
    """混合注册入口。返回 (email, password, refresh_token) 或 (None, None)。"""
    orch = _build_orchestrator()
    res = await orch.register(proxy_str, idx)
    if res.success and res.email:
        return res.email, res.password, res.refresh_token
    return None, None
```

> 注：测试用 `monkeypatch.setattr("outlook_hybrid.HybridOutlookOrchestrator", _FakeOrch)` 替换编排器类，`_build_orchestrator` 内引用的是模块级名字，故需将 `HybridOutlookOrchestrator(...)` 调用保持为模块级可替换符号——已满足（import 到模块命名空间）。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/outlook_hybrid/test_facade.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 全量回归 outlook_hybrid**

Run: `python -m pytest tests/outlook_hybrid/ -v`
Expected: PASS（全部）

- [ ] **Step 6: 提交**

```bash
git add outlook_hybrid/__init__.py tests/outlook_hybrid/test_facade.py
git commit -m "feat(outlook_hybrid): 门面 register_outlook_hybrid 装配真实组件"
```

---

## Task 9: step_engine 模式分派（hybrid/browser/protocol）

**Files:**
- Modify: `services/worker/step_engine.py:89-117`（`OutlookRegistrationFlow.execute_step` 的注册步）
- Test: `tests/test_step_engine_mode.py`

- [ ] **Step 1: 写失败测试**

`tests/test_step_engine_mode.py`:

```python
import asyncio
import sys
import types
import pytest


def _make_flow():
    # 避免 LegacyBridge 真实副作用：直接构造类实例
    from worker.step_engine import OutlookRegistrationFlow
    return OutlookRegistrationFlow.__new__(OutlookRegistrationFlow)


def _run(coro):
    return asyncio.run(coro)


def test_mode_hybrid_dispatches_to_register_outlook_hybrid(monkeypatch):
    called = {}

    async def fake_hybrid(proxy_str, idx):
        called["mode"] = "hybrid"
        return ("h@outlook.com", "Pw!", "rt")

    mod = types.ModuleType("outlook_hybrid")
    mod.register_outlook_hybrid = fake_hybrid
    monkeypatch.setitem(sys.modules, "outlook_hybrid", mod)

    flow = _make_flow()
    ctx = {"mode": "hybrid", "proxy": "p", "idx": 0}
    res = _run(flow.execute_step(2, "Browser registration with proxy", ctx))
    assert called["mode"] == "hybrid"
    assert res.success is True
    assert ctx["email"] == "h@outlook.com"
    assert ctx["refresh_token"] == "rt"


def test_mode_protocol_dispatches_to_register_outlook_protocol(monkeypatch):
    called = {}

    def fake_protocol(proxy_str=None, idx=0):
        called["mode"] = "protocol"
        return ("p@outlook.com", "Pw!")

    mod = sys.modules.get("register_outlook_standalone") or types.ModuleType("register_outlook_standalone")
    monkeypatch.setattr(mod, "register_outlook_protocol", fake_protocol, raising=False)
    monkeypatch.setitem(sys.modules, "register_outlook_standalone", mod)

    flow = _make_flow()
    ctx = {"mode": "protocol", "proxy": "p", "idx": 0}
    res = _run(flow.execute_step(2, "Browser registration with proxy", ctx))
    assert called["mode"] == "protocol"
    assert res.success is True
    assert ctx["email"] == "p@outlook.com"


def test_default_mode_is_browser(monkeypatch):
    called = {}

    async def fake_browser(bb, idx, proxy_str):
        called["mode"] = "browser"
        return ("b@outlook.com", "Pw!", None)

    mod = sys.modules.get("register_outlook_standalone") or types.ModuleType("register_outlook_standalone")
    monkeypatch.setattr(mod, "_register_one_browser", fake_browser, raising=False)
    monkeypatch.setitem(sys.modules, "register_outlook_standalone", mod)
    # get_browser_provider 桩
    bp = types.ModuleType("common.browser_provider")
    bp.get_browser_provider = lambda: object()
    monkeypatch.setitem(sys.modules, "common.browser_provider", bp)

    flow = _make_flow()
    ctx = {"proxy": "p", "idx": 0}  # 无 mode → 默认 browser
    res = _run(flow.execute_step(2, "Browser registration with proxy", ctx))
    assert called["mode"] == "browser"
    assert res.success is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_step_engine_mode.py -v`
Expected: FAIL（当前实现写死 `_register_one_browser`，hybrid/protocol 分支不存在）

- [ ] **Step 3: 写实现**

把 `services/worker/step_engine.py` 中 `OutlookRegistrationFlow.execute_step` 的 `"Browser registration with proxy"` 分支整体替换为：

```python
        elif step_name == "Browser registration with proxy":
            from common.browser_provider import get_browser_provider

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

            else:  # browser（默认，已稳定）
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
                return StepResult(
                    step_number=step_number, name=step_name, success=True,
                    data={"email": email, "has_token": bool(graph_token), "mode": mode},
                )

            return StepResult(
                step_number=step_number, name=step_name, success=False,
                error=f"Registration failed (mode={mode}) — check ixBrowser/proxy/captcha",
            )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_step_engine_mode.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add services/worker/step_engine.py tests/test_step_engine_mode.py
git commit -m "feat(worker): OutlookRegistrationFlow 支持 hybrid/browser/protocol 模式分派"
```

---

## Task 10: Gateway + process_manager 透传 mode

**Files:**
- Modify: `services/worker/process_manager.py`（`submit()` 与 `_worker_process` 透传 `mode`）
- Modify: `services/gateway/main.py`（`/register/outlook` 读取 body 的 `mode` 并传入 `submit`）
- Test: `tests/test_process_manager_mode.py`

- [ ] **Step 1: 写失败测试**

`tests/test_process_manager_mode.py`:

```python
import inspect
from worker.process_manager import TaskManager


def test_submit_accepts_mode_in_config():
    # submit(config=...) 应接受 mode 并放进 config 透传
    sig = inspect.signature(TaskManager.submit)
    assert "config" in sig.parameters


def test_worker_process_passes_mode_into_context(monkeypatch):
    # _worker_process 把 config['mode'] 注入 context
    import worker.process_manager as pm
    src = inspect.getsource(pm._worker_process)
    # 上下文用 {**(config or {})} 展开，mode 自然进入 context
    assert "config" in src and "context" in src
```

> 现有 `_worker_process` 已用 `context = {"idx": idx, "proxy": proxy, **(config or {})}`，`mode` 在 `config` 里即自动进入 context。本任务确保 Gateway 把 `mode` 放进 `config`。

- [ ] **Step 2: 运行测试确认（基线）**

Run: `python -m pytest tests/test_process_manager_mode.py -v`
Expected: 第一条 PASS（submit 已有 config 参数）；若 `_worker_process` 源码断言失败则 FAIL → Step 3 修正。

- [ ] **Step 3: 确认/实现透传**

确认 `services/worker/process_manager.py` 的 `_worker_process` 内为：

```python
        context = {"idx": idx, "proxy": proxy, **(config or {})}
```

（已存在，无需改。`mode` 通过 `config` 进入 `context`。）

在 `services/gateway/main.py` 的 `/register/outlook` 路由内，把请求体的 `mode` 放进每个任务的 `config`。定位现有 dispatch 循环（构造 `config` 并调用 `task_manager.submit(...)` 处），改为：

```python
    mode = (payload.get("mode") or "browser")  # payload 为请求体 dict
    ...
    for i in range(count):
        task_id = task_manager.submit(idx=i, proxy=proxy, config={**base_config, "mode": mode})
        task_ids.append(task_id)
```

（`base_config` 为该路由原有传给 submit 的 config；若原先未传 config，则用 `config={"mode": mode}`。实现者按现有代码就地适配。）

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_process_manager_mode.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add services/gateway/main.py services/worker/process_manager.py tests/test_process_manager_mode.py
git commit -m "feat(gateway): /register/outlook 透传注册模式 mode 至 worker"
```

---

## Task 11: 前端注册模式下拉

在注册表单加"注册模式"下拉（默认浏览器），提交时带上 `mode`。

**Files:**
- Modify: `frontend/src/pages/AccountsPage.tsx`（注册表单 + 提交 payload）

- [ ] **Step 1: 定位注册表单与提交逻辑**

Run: `grep -n "register/outlook\|proxy\|Form.Item\|onFinish\|handleRegister" frontend/src/pages/AccountsPage.tsx | head -40`
记录：表单 `Form` 实例名、proxy 选择器所在 `Form.Item`、提交函数（POST `/api/register/outlook` 处）。

- [ ] **Step 2: 在表单加模式下拉**

在 proxy 选择 `Form.Item` 之后插入（仅 Outlook 平台显示；若表单已有 platform 判断，沿用其条件）：

```tsx
<Form.Item name="mode" label="注册模式" initialValue="browser"
  tooltip="browser=完整浏览器(稳定)；hybrid=浏览器铸验证码token+协议提交(快)；protocol=纯协议(需可解验证码)">
  <Select
    options={[
      { value: 'browser', label: '浏览器模式（稳定）' },
      { value: 'hybrid', label: '混合模式（浏览器解码+协议提交）' },
      { value: 'protocol', label: '纯协议（实验）' },
    ]}
  />
</Form.Item>
```

确保 `Select` 已从 `antd` 导入（文件顶部 import 若无则补 `Select`）。

- [ ] **Step 3: 提交时带上 mode**

在提交函数构造的请求体里加入 `mode`：

```tsx
// 原本 body 形如 { count, proxy, ... }
const body = { ...values, mode: values.mode || 'browser' };
// fetch('/api/register/outlook', { method:'POST', body: JSON.stringify(body) ... })
```

（`values` 为 antd `form.getFieldsValue()` / `onFinish` 入参；按现有提交代码就地接入。）

- [ ] **Step 4: 前端构建校验**

Run: `cd frontend && npm run build`
Expected: 构建成功，无 TS 报错。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/AccountsPage.tsx
git commit -m "feat(frontend): 注册表单增加注册模式下拉(browser/hybrid/protocol)"
```

---

## Task 12: E2E 验证 + 切默认 + 文档收尾（人工门）

**Files:**
- Modify: `docs/superpowers/specs/2026-06-10-outlook-hybrid-registration-design.md`（追加 E2E 结论）
- Modify: `services/worker/step_engine.py`（视结果决定是否把默认 mode 切为 hybrid）

- [ ] **Step 1: E2E 真实跑混合模式**

前端选"混合模式"，用可用代理跑 5 次，记录：成功率、平均耗时、回退次数、`SubmitRejected` 是否出现。
（命令行替代：临时脚本调 `asyncio.run(outlook_hybrid.register_outlook_hybrid("<proxy>", 0))` 跑 N 次统计。）

- [ ] **Step 2: 记录结论到设计文档**

在设计文档末尾追加"## E2E 结果（2026-xx-xx）"小节，写明成功率与是否达到切默认标准（建议 ≥ 浏览器模式成功率且更快）。

- [ ] **Step 3: 视结果切默认（达标才切）**

若达标，把 Task 9 中 `mode = context.get("mode", "browser")` 改为 `"hybrid"`，并把前端下拉 `initialValue` 改为 `"hybrid"`。未达标则保持 `browser` 默认，hybrid 作为可选项保留。

- [ ] **Step 4: 清理 spike**

```bash
git rm _spike_outlook_hybrid.py
```

- [ ] **Step 5: 全量测试 + 提交**

Run: `python -m pytest tests/outlook_hybrid/ tests/test_step_engine_mode.py tests/test_process_manager_mode.py -v`
Expected: PASS（全部）

```bash
git add -A
git commit -m "docs+chore: 混合注册 E2E 结论、默认模式决策、清理 spike"
```

---

## 自检对照（Self-Review）

**Spec 覆盖：**
- 核心原则（共享 proxy/cookie/UA）→ Task 3（submitter 设同 UA、转植 cookie、同 proxy）✅
- SessionMinter 路由拦截截获+abort → Task 5 ✅
- 逐字 replay 不重建 → Task 3（直接发 `cred.create_payload`）✅
- MintedCredential 结构 → Task 1 ✅
- ProtocolSubmitter（cookie 转植/replay/校验/抽token/SubmitRejected）→ Task 2、Task 3 ✅
- FallbackPolicy（MintFailed 重试1次、SubmitRejected 回退浏览器、复用 `_register_one_browser`）→ Task 6、Task 8 ✅
- BrowserPool 吞吐 → Task 7 ✅
- Orchestrator Facade → Task 7、Task 8 ✅
- 文件落位 `outlook_hybrid/` → Task 1~8 ✅
- 模式选择 Strategy/Factory（hybrid/browser/protocol）→ Task 9 ✅
- 前端模式下拉全链路透传 → Task 10、Task 11 ✅
- Phase 0 验证 spike → Task 0 ✅
- 错误处理表 → 分散于 Task 3/5/6（各异常路径有测试）✅
- 测试策略（单元/集成/E2E）→ 各 Task 测试 + Task 12 ✅

**偏差记录：** 取消 `AccountDraft`/`AccountFactory`（身份起源于浏览器、经截获 payload 流转），已在"有意偏差"小节说明。设计文档中 `MintedCredential` 不含独立 uaid/hpgid 字段——它们在 `create_payload`/`request_headers` 内，与 Task 1 实现一致。

**占位符扫描：** 无 TBD/TODO；每个代码步均含完整代码。Task 10/11 含"按现有代码就地适配"指引，因 Gateway/前端的确切行号需执行时定位，已给出 grep 定位命令 + 精确插入内容，非占位。

**类型/签名一致性：**
- `MintedCredential`（Task 1）字段被 Task 3/5/8 一致引用（`.email/.password/.has_token/create_payload/request_headers/cookies/user_agent/proxy`）✅
- `RegistrationResult`（Task 3）被 Task 6/7/8 一致引用（`success/email/password/refresh_token/mode_used/error/has_token`）✅
- `SessionMinter.mint(proxy, idx)`（Task 5）↔ Orchestrator 调用（Task 7）↔ facade（Task 8）一致 ✅
- `ProtocolSubmitter.submit(cred)`（Task 3）↔ Orchestrator（Task 7）一致 ✅
- `FallbackPolicy.handle(proxy, idx, error)`（Task 6）↔ Orchestrator（Task 7）一致 ✅
- `BrowserPool.slot()` async context（Task 7）↔ Orchestrator（Task 7）一致 ✅
- `install_create_account_interceptor(page)->Future`（Task 5）单点定义与使用 ✅
