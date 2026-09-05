# Ant Browser Provider 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `common/ant_provider.py` 实现 `BrowserProvider` 抽象,走 Ant Browser 本地 REST API(19876),并把 `BROWSER_PROVIDER` 默认切为 `ant`,使 reg-factory 用 Ant 替代 ixBrowser 开窗口。

**Architecture:** `AntBrowserProvider` 用 urllib 调 Ant REST API,风格对齐 `common/donut_provider.py`(自定义异常 + 网络抖动重试)。7 个抽象方法映射到 create/launch/stop/delete/list。生命周期沿用 ixBrowser 模式,上层 worker/flows 零改造。工厂 `get_browser_provider()` 加 `ant` 分支。

**Tech Stack:** Python 3.11(根用 3.10+),urllib,pytest,unittest.mock。Ant Browser Go 服务端(只读对接,不改)。

**设计依据:** `docs/superpowers/specs/2026-09-05-ant-browser-provider-design.md`

**运行环境提醒:** 本机裸 `python` 指向 hermes-agent 全局 venv。根目录测试用 `services/.venv/Scripts/python.exe`(它装了根 requirements),或按项目惯例。跑根测试:`cd F:/reg-factory && ./services/.venv/Scripts/python.exe -m pytest tests/ -q`。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `common/ant_provider.py` | **新建** `AntBrowserProvider` + `AntAPIError`,唯一持有 Ant REST 调用逻辑 |
| `tests/test_ant_provider.py` | **新建** mock `_call` 的单测 |
| `config.py` | **改** 默认 `BROWSER_PROVIDER=ant`,新增 `ANT_API_BASE`/`ANT_API_KEY` |
| `common/browser_provider.py` | **改** 工厂加 `ant` 分支 |
| `.env.example` | **改** provider 段默认 ant |
| `README.md` / `AGENTS.md` | **改** 前置条件与 provider 说明 |

---

### Task 1: config.py 增加 Ant 配置

**Files:**
- Modify: `config.py:27-35`

- [ ] **Step 1: 改配置**

`config.py` 中把 provider 段(第 27-35 行)替换为:

```python
# 浏览器 provider：默认 ant（Ant Browser 本地 API 端口 19876）。
# 可用 BROWSER_PROVIDER=ixbrowser / donut 切换。
BROWSER_PROVIDER = _env("BROWSER_PROVIDER", "ant")
ANT_API_BASE = _env("ANT_API_BASE", "http://127.0.0.1:19876")
ANT_API_KEY = _env("ANT_API_KEY", "")
DONUT_API_BASE = _env("DONUT_API_BASE", "http://127.0.0.1:10108")
DONUT_API_TOKEN = _env("DONUT_API_TOKEN", "")
DONUT_PROFILE_REUSE = _env("DONUT_PROFILE_REUSE", "true").lower() == "true"
IXBROWSER_TARGET = _env("IXBROWSER_TARGET", "127.0.0.1")
IXBROWSER_PORT = int(_env("IXBROWSER_PORT", "53200"))
IXBROWSER_KERNEL_VERSION = _env("IXBROWSER_KERNEL_VERSION", "")
```

- [ ] **Step 2: 验证导入**

```bash
cd F:/reg-factory && ./services/.venv/Scripts/python.exe -c "import config; print('BROWSER_PROVIDER=', config.BROWSER_PROVIDER, 'ANT_API_BASE=', config.ANT_API_BASE, 'ANT_API_KEY=', repr(config.ANT_API_KEY))"
```
Expected: `BROWSER_PROVIDER= ant ANT_API_BASE= http://127.0.0.1:19876 ANT_API_KEY= ''`

(若本机 `.env` 里设了 `BROWSER_PROVIDER`,会覆盖默认值,属正常)

- [ ] **Step 3: 提交**

```bash
git add config.py
git commit -m "feat(config): 默认 provider 改 ant，新增 ANT_API_BASE/ANT_API_KEY"
```

---

### Task 2: AntBrowserProvider HTTP 底座 + create_browser

**Files:**
- Create: `common/ant_provider.py`
- Test: `tests/test_ant_provider.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_ant_provider.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from common.ant_provider import AntBrowserProvider, AntAPIError
from common.browser_provider import BrowserProvider


def _provider_with_fake_call():
    p = AntBrowserProvider(base="http://127.0.0.1:19876", api_key="")
    p._call = MagicMock()      # 注入 fake，绕过真实 HTTP
    return p, p._call


def test_is_browser_provider():
    assert isinstance(AntBrowserProvider(), BrowserProvider)


def test_create_browser_direct_when_no_proxy():
    p, call = _provider_with_fake_call()
    call.return_value = {"profileId": "uuid-1", "ok": True}
    pid = p.create_browser(name="reg_1", proxy_str=None)
    assert pid == "uuid-1"
    method, path, body = call.call_args[0]
    assert method == "POST" and path == "/api/profiles"
    assert body["profile"]["profileName"] == "reg_1"
    assert body["profile"]["proxyConfig"] == "direct://"


def test_create_browser_passes_proxy_str_as_proxyconfig():
    p, call = _provider_with_fake_call()
    call.return_value = {"profileId": "uuid-2"}
    p.create_browser(name="reg", proxy_str="http://u:p@1.2.3.4:8080")
    body = call.call_args[0][2]
    assert body["profile"]["proxyConfig"] == "http://u:p@1.2.3.4:8080"


def test_create_browser_empty_proxy_is_direct():
    p, call = _provider_with_fake_call()
    call.return_value = {"profileId": "uuid-3"}
    p.create_browser(name="reg", proxy_str="   ")
    assert call.call_args[0][2]["profile"]["proxyConfig"] == "direct://"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd F:/reg-factory && ./services/.venv/Scripts/python.exe -m pytest tests/test_ant_provider.py -q
```
Expected: FAIL — `ModuleNotFoundError: No module named 'common.ant_provider'`

- [ ] **Step 3: 写实现（底座 + create）**

创建 `common/ant_provider.py`:

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd F:/reg-factory && ./services/.venv/Scripts/python.exe -m pytest tests/test_ant_provider.py -q
```
Expected: PASS,4 passed(is_browser_provider + 3 个 create)

- [ ] **Step 5: 提交**

```bash
git add common/ant_provider.py tests/test_ant_provider.py
git commit -m "feat(ant): AntBrowserProvider HTTP 底座与 create_browser"
```

---

### Task 3: open_browser（launch 拿 debugPort）

**Files:**
- Modify: `common/ant_provider.py`(追加方法)
- Test: `tests/test_ant_provider.py`(追加)

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_ant_provider.py`:

```python
def test_open_browser_returns_http_endpoint_from_debugport():
    p, call = _provider_with_fake_call()
    call.return_value = {"debugPort": 46602, "debugReady": True, "ok": True}
    data = p.open_browser("uuid-1")
    assert data == {"ws": "http://127.0.0.1:46602", "http": "http://127.0.0.1:46602"}
    method, path, body = call.call_args[0]
    assert method == "POST" and path == "/api/launch"
    assert body == {"profileId": "uuid-1"}


def test_open_browser_polls_when_launch_not_ready():
    p, call = _provider_with_fake_call()
    # 第一次 launch 未就绪,随后 runtime/active 就绪
    call.side_effect = [
        {"debugReady": False, "debugPort": 0},                        # launch
        {"profileId": "uuid-1", "debugReady": True, "debugPort": 55000},  # runtime/active
    ]
    data = p.open_browser("uuid-1")
    assert data["http"] == "http://127.0.0.1:55000"


def test_open_browser_raises_when_never_ready():
    p, call = _provider_with_fake_call()
    call.return_value = {"debugReady": False, "debugPort": 0}
    with patch("common.ant_provider.time.sleep"):      # 免真 sleep 15s
        with pytest.raises(AntAPIError):
            p.open_browser("uuid-1")
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd F:/reg-factory && ./services/.venv/Scripts/python.exe -m pytest tests/test_ant_provider.py -q -k open_browser
```
Expected: FAIL — `open_browser` 目前是 `raise NotImplementedError` 占位,3 个测试均因 NotImplementedError 报红。

- [ ] **Step 3: 写实现（替换占位）**

把 `common/ant_provider.py` 里 `open_browser` 的 `raise NotImplementedError` 占位替换为:

```python
    def open_browser(self, profile_id):
        r = self._call("POST", "/api/launch", {"profileId": profile_id})
        debug_port = r.get("debugPort")
        if r.get("debugReady") and debug_port:
            ep = f"http://127.0.0.1:{debug_port}"
            return {"ws": ep, "http": ep}
        # 兜底:短轮询 runtime/active(实测通常 launch 即就绪,此为极端兜底)
        for _ in range(15):
            rt = self._call("GET", "/api/runtime/active")
            if rt.get("profileId") == profile_id and rt.get("debugReady") and rt.get("debugPort"):
                ep = f"http://127.0.0.1:{rt['debugPort']}"
                return {"ws": ep, "http": ep}
            time.sleep(1)
        raise AntAPIError(0, "GET", "/api/runtime/active", "debug not ready")
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd F:/reg-factory && ./services/.venv/Scripts/python.exe -m pytest tests/test_ant_provider.py -q
```
Expected: PASS,7 passed(前 4 + 新 3)

注意 `test_open_browser_raises_when_never_ready`(Step 1 里已用 `patch("common.ant_provider.time.sleep")` 包裹)会走 15 次轮询,patch 掉 sleep 后瞬时完成。`patch` 已在 Step 1 的测试文件顶部 import。该测试恒返回未就绪,15 次轮询耗尽后抛 `AntAPIError`。若这条测试实际很慢,确认 sleep 的 patch 路径是 `common.ant_provider.time.sleep`(模块内 `import time` 后用 `time.sleep`)。

- [ ] **Step 5: 提交**

```bash
git add common/ant_provider.py tests/test_ant_provider.py
git commit -m "feat(ant): open_browser 走 launch 拿 debugPort，兜底轮询 runtime/active"
```

---

### Task 4: close / delete / cleanup / list / select

**Files:**
- Modify: `common/ant_provider.py`(追加)
- Test: `tests/test_ant_provider.py`(追加)

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_ant_provider.py`:

```python
def test_close_browser_stops_with_profile_selector():
    p, call = _provider_with_fake_call()
    call.return_value = {"ok": True}
    p.close_browser("uuid-1")
    method, path, body = call.call_args[0]
    assert method == "POST" and path == "/api/runtime/stop"
    assert body == {"profileId": "uuid-1"}


def test_close_browser_swallows_errors():
    p, call = _provider_with_fake_call()
    call.side_effect = AntAPIError(400, "POST", "/api/runtime/stop", "bad")
    p.close_browser("uuid-1")   # 不抛


def test_delete_browser_stops_then_deletes():
    p, call = _provider_with_fake_call()
    call.return_value = {"ok": True}
    p.delete_browser("uuid-1")
    paths = [c[0][1] for c in call.call_args_list]
    assert "/api/runtime/stop" in paths
    assert "/api/profiles/uuid-1" in paths


def test_delete_browser_swallows_errors():
    p, call = _provider_with_fake_call()
    call.side_effect = AntAPIError(409, "DELETE", "/api/profiles/uuid-1", "running")
    p.delete_browser("uuid-1")   # 不抛


def test_list_browsers_maps_fields():
    p, call = _provider_with_fake_call()
    call.return_value = {"count": 2, "items": [
        {"profileId": "a", "profileName": "n1", "userDataDir": "d1"},
        {"profileId": "b", "profileName": "n2", "userDataDir": "d2"},
    ]}
    out = p.list_browsers()
    rows = out["data"]["list"]
    assert rows[0] == {"id": "a", "name": "n1", "remark": "d1", "seq": "a"}
    assert len(rows) == 2


def test_cleanup_browsers_deletes_beyond_keep():
    p, call = _provider_with_fake_call()
    # 第一次 _call 是 GET /api/profiles(列表),之后是 stop/delete(吞异常)
    call.side_effect = [
        {"items": [{"profileId": "a"}, {"profileId": "b"}, {"profileId": "c"}]},
    ] + [{"ok": True}] * 10
    n = p.cleanup_browsers(keep=1)
    assert n == 2   # 保留 1 个,删 2 个
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd F:/reg-factory && ./services/.venv/Scripts/python.exe -m pytest tests/test_ant_provider.py -q -k "close or delete or list or cleanup"
```
Expected: FAIL — close/delete/cleanup/list 目前是 `raise NotImplementedError` 占位,相关测试报红。

- [ ] **Step 3: 写实现（替换 5 个占位）**

把 `common/ant_provider.py` 里 `close_browser`/`delete_browser`/`list_browsers`/`cleanup_browsers`/`select_browser` 的 `raise NotImplementedError` 占位,以及新增 `_fetch_all_profiles`,替换/追加为:

```python
    def close_browser(self, profile_id):
        try:
            self._call("POST", "/api/runtime/stop", {"profileId": profile_id})
        except Exception:
            pass

    def delete_browser(self, profile_id):
        # delete 对运行中实例返回 409,必须先 stop
        try:
            self._call("POST", "/api/runtime/stop", {"profileId": profile_id})
        except Exception:
            pass
        try:
            self._call("DELETE", f"/api/profiles/{profile_id}", None)
        except Exception:
            pass

    def _fetch_all_profiles(self):
        return self._call("GET", "/api/profiles").get("items", [])

    def list_browsers(self, page=0, page_size=100):
        rows = [{
            "id": p.get("profileId"),
            "name": p.get("profileName", ""),
            "remark": p.get("userDataDir", ""),
            "seq": p.get("profileId", ""),
        } for p in self._fetch_all_profiles()]
        return {"data": {"list": rows}}

    def cleanup_browsers(self, keep=0):
        rows = self._fetch_all_profiles()
        to_delete = rows[keep:]
        for p in to_delete:
            self.delete_browser(p.get("profileId"))
        return len(to_delete)

    def select_browser(self):
        rows = self._fetch_all_profiles()
        print("\n可用的浏览器实例:")
        print("-" * 50)
        if rows:
            for i, p in enumerate(rows):
                print(f"  [{i}] {p.get('profileId')}  {p.get('profileName', '未命名')}")
        else:
            print("  (无)")
        print("  [n] 创建新实例")
        print("-" * 50)
        while True:
            max_idx = len(rows) - 1 if rows else -1
            hint = f"[0-{max_idx}/n]" if rows else "[n]"
            choice = input(f"请选择 {hint}: ").strip().lower()
            if choice == "n":
                name = input("实例名称 (留空自动): ").strip() or f"reg_{len(rows) + 1}"
                return self.create_browser(name=name)
            if rows and choice.isdigit() and 0 <= int(choice) < len(rows):
                return rows[int(choice)].get("profileId")
            print("无效选择,请重新输入。")
```

- [ ] **Step 4: 跑测试确认通过（全文件）**

```bash
cd F:/reg-factory && ./services/.venv/Scripts/python.exe -m pytest tests/test_ant_provider.py -q
```
Expected: PASS,13 passed

- [ ] **Step 5: 提交**

```bash
git add common/ant_provider.py tests/test_ant_provider.py
git commit -m "feat(ant): close/delete(先停再删)/cleanup/list/select 实现"
```

---

### Task 5: 工厂加 ant 分支

**Files:**
- Modify: `common/browser_provider.py:44-56`(`get_browser_provider`)
- Test: `tests/test_ant_provider.py`(追加)

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_ant_provider.py`:

```python
def test_factory_returns_ant_when_configured(monkeypatch):
    import common.browser_provider as bp
    monkeypatch.setattr("config.BROWSER_PROVIDER", "ant", raising=False)
    bp._PROVIDER = None            # 重置单例
    p = bp.get_browser_provider()
    assert isinstance(p, AntBrowserProvider)
    bp._PROVIDER = None            # 清理,免污染其它测试
```

注意:`get_browser_provider` 在函数内 `from config import BROWSER_PROVIDER`,故 monkeypatch 需打在 `config.BROWSER_PROVIDER`。

- [ ] **Step 2: 跑测试确认失败**

```bash
cd F:/reg-factory && ./services/.venv/Scripts/python.exe -m pytest tests/test_ant_provider.py -q -k factory_returns_ant
```
Expected: FAIL — 工厂无 ant 分支,落到 else 返回 IXBrowserProvider,断言 isinstance AntBrowserProvider 失败

- [ ] **Step 3: 改工厂**

`common/browser_provider.py` 的 `get_browser_provider`,把 if/else 改为:

```python
def get_browser_provider():
    """返回全局单例 provider。默认 ant，可用 BROWSER_PROVIDER=ixbrowser/donut 切换。"""
    global _PROVIDER
    if _PROVIDER is None:
        from config import BROWSER_PROVIDER
        if BROWSER_PROVIDER == "ant":
            from common.ant_provider import AntBrowserProvider
            _PROVIDER = AntBrowserProvider()
        elif BROWSER_PROVIDER == "donut":
            from common.donut_provider import DonutBrowserProvider
            _PROVIDER = DonutBrowserProvider()
        else:
            from common.ixbrowser_provider import IXBrowserProvider
            _PROVIDER = IXBrowserProvider()
    return _PROVIDER
```

同时更新模块顶部 docstring 里「默认 ixBrowser」的措辞为「默认 ant」。

- [ ] **Step 4: 跑测试确认通过 + 工厂既有测试不回归**

```bash
cd F:/reg-factory && ./services/.venv/Scripts/python.exe -m pytest tests/test_ant_provider.py tests/test_browser_provider.py -q
```
Expected: PASS。注意 `tests/test_browser_provider.py::test_factory_returns_browser_provider` 现在会实例化 AntBrowserProvider(默认 ant),它不发网络请求(只存 base),isinstance BrowserProvider 成立,通过。

- [ ] **Step 5: 提交**

```bash
git add common/browser_provider.py tests/test_ant_provider.py
git commit -m "feat(ant): 工厂加 ant 分支，默认走 AntBrowserProvider"
```

---

### Task 6: 文档更新

**Files:**
- Modify: `.env.example`、`README.md`、`AGENTS.md`

- [ ] **Step 1: 改 .env.example**

`.env.example` 的 provider 段(顶部)替换为:

```
# ---------------- 浏览器 provider ----------------
# ant（默认）/ ixbrowser / donut
BROWSER_PROVIDER=ant
ANT_API_BASE=http://127.0.0.1:19876
# Ant Browser 设置页开启 API 认证时填(默认空=不校验)
ANT_API_KEY=

# ixbrowser 是备选 provider
IXBROWSER_TARGET=127.0.0.1
IXBROWSER_PORT=53200
IXBROWSER_KERNEL_VERSION=

# donut 是备选 provider
DONUT_API_BASE=http://127.0.0.1:10108
# 留空时从 DonutBrowserDev 本地设置自动读取 token
DONUT_API_TOKEN=
DONUT_PROFILE_REUSE=true
```

- [ ] **Step 2: 改 README.md**

在 README 里找到浏览器 provider 说明与前置条件两处(grep `provider` 与 `DonutBrowser`/`ixBrowser` 定位),把默认 provider 描述改为:

- 功能段的「浏览器 provider」行改为:「默认 Ant Browser(本地 API 19876),可切 ixBrowser / donut。」
- 前置条件段改为:「Ant Browser 正在运行,设置页已启用启动 API 服务(默认端口 19876);或自行设 `BROWSER_PROVIDER=ixbrowser`/`donut`。」

- [ ] **Step 3: 改 AGENTS.md**

`AGENTS.md` 里 provider 那行(grep `BROWSER_PROVIDER`)改为:

```
- `BROWSER_PROVIDER=ant` is the default (Ant Browser local API on `127.0.0.1:19876`). Set `ixbrowser` or `donut` to use those instead.
```

- [ ] **Step 4: 校验一致性**

```bash
cd F:/reg-factory && grep -rn "BROWSER_PROVIDER" config.py .env.example AGENTS.md README.md | grep -iE "ant|default|默认"
```
Expected: 四处都体现默认 ant,无残留「默认 ixbrowser」。

- [ ] **Step 5: 提交**

```bash
git add .env.example README.md AGENTS.md
git commit -m "docs: provider 默认改 Ant Browser，补 ANT_API_BASE/ANT_API_KEY 说明"
```

---

### Task 7: 真实 smoke 验证（需显式授权，产生副作用）

**Files:** 无代码改动

> **需要用户授权:** 本任务会真实启动 Ant 浏览器窗口、消耗一次代理连接。执行前先向用户确认。前提:Ant Browser 在 19876 运行。

- [ ] **Step 1: 跑全部单测(确认无回归)**

```bash
cd F:/reg-factory && ./services/.venv/Scripts/python.exe -m pytest tests/ -q
```
Expected: 全绿。

- [ ] **Step 2: 真实链路 smoke（用 provider 走 create→open→CDP连接→teardown）**

```bash
cd F:/reg-factory && ./services/.venv/Scripts/python.exe - <<'PYEOF'
import asyncio, sys
sys.path.insert(0, '.')
from common.ant_provider import AntBrowserProvider

async def main():
    from playwright.async_api import async_playwright
    p = AntBrowserProvider()
    pid = p.create_browser(name="__smoke__", proxy_str=None)   # 直连
    print("created:", pid)
    try:
        data = p.open_browser(pid)
        print("open:", data)
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(data["ws"])
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto("https://httpbin.org/ip", timeout=30000, wait_until="domcontentloaded")
            body = await page.inner_text("body")
            print("page body:", body[:120])
            await browser.close()
    finally:
        p.close_browser(pid)
        p.delete_browser(pid)
        print("cleaned up")

asyncio.run(main())
PYEOF
```
Expected: 打印 created/open/page body(含出口 IP)/cleaned up。CDP 连接成功、页面能加载即验证通过。

- [ ] **Step 3: 用一条真实代理验证出口 IP（spec 第 9 节边界项）**

把 Step 2 脚本的 `proxy_str=None` 改为一条真实 Webshare 代理(`http://用户:密码@host:port`),重跑,确认 `page body` 里的出口 IP 是该代理的 IP,而非本机 IP。验证代理经 Ant 正确生效。

- [ ] **Step 4: 确认无残留 profile**

```bash
cd F:/reg-factory && ./services/.venv/Scripts/python.exe -c "
import json,urllib.request
j=json.load(urllib.request.urlopen('http://127.0.0.1:19876/api/profiles'))
names=[i.get('profileName') for i in j.get('items',[])]
print('profiles:', names)
print('smoke 残留:', [n for n in names if '__smoke__' in str(n)] or '无')
"
```
Expected: `smoke 残留: 无`

---

## 完成标准

- [ ] `./services/.venv/Scripts/python.exe -m pytest tests/ -q` 全绿(含 test_ant_provider 的 14 项)
- [ ] `BROWSER_PROVIDER` 默认 ant,config/.env.example/README/AGENTS 四处一致
- [ ] smoke:AntBrowserProvider 能 create→open→Playwright connect_over_cdp 加载页面→teardown,无残留 profile
- [ ] 一条真实代理经 Ant 出口 IP 正确
