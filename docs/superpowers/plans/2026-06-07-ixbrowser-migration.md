# BitBrowser → ixBrowser 迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 reg-factory 的指纹浏览器后端从 BitBrowser 彻底替换为 ixBrowser，对上层调用方保持接口兼容。

**Architecture:** 新增抽象基类 `BrowserProvider` 定义浏览器窗口契约（create/open/close/delete/cleanup/list/select），由唯一实现 `IXBrowserProvider`（基于 `ixbrowser-local-api`）落地；方法名与返回形状刻意对齐旧 `BitBrowser`，让 7 个调用文件只改 import 与实例化。删除 `bitbrowser.py` 与 `register_outlook_standalone.py` 内的重复封装类。

**Tech Stack:** Python 3.10+、`ixbrowser-local-api`、Playwright（CDP 连接不变）、pytest（新增，仅用于纯逻辑/mock 单测）。

**设计依据：** `docs/superpowers/specs/2026-06-07-ixbrowser-migration-design.md`
**参考实现：** `D:\workspace\projects\auto_bitbrowser2`（`services/ix_api.py`、`services/ix_window.py`、`ixbrowser_local_api`）

---

## 文件结构

| 文件 | 责任 | 动作 |
|---|---|---|
| `common/browser_provider.py` | `BrowserProvider` 抽象基类 + `get_browser_provider()` 工厂 | 新建 |
| `common/ixbrowser_provider.py` | `IXBrowserProvider` 实现（client 重试、代理解析、指纹、字段转换） | 新建 |
| `tests/test_ixbrowser_provider.py` | provider 纯逻辑/mock 单测 | 新建 |
| `tests/conftest.py` | 让 `import config` 等可被测试发现（sys.path） | 新建 |
| `requirements.txt` | 加 `ixbrowser-local-api` | 改 |
| `requirements-dev.txt` | 加 `pytest`（新建） | 新建 |
| `config.py` | 去 `BITBROWSER_API`，加 `IXBROWSER_TARGET/PORT` | 改 |
| `common/browser.py` | 改用 `get_browser_provider()` | 改 |
| `register.py` | 改 import / 实例化 | 改 |
| `register_grok.py` | 改 import / 实例化 | 改 |
| `register_outlook_standalone.py` | 删 `BitBrowserClient` 类，改用 provider，迁移 `_parse_proxy` 调用 | 改 |
| `outlook_reg_loop.py` | 改 `bb` 来源为 `get_browser_provider()` | 改 |
| `mailbox_broker.py` | 改 import / 实例化 | 改 |
| `validate_keys.py` | 改 import / 实例化 | 改 |
| `bitbrowser.py` | 删除 | 删 |
| `.env.example` / `README.md` | 配置/前置条件改 ixBrowser | 改 |

---

## Task 1: 依赖与测试基建

**Files:**
- Modify: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `tests/conftest.py`

- [ ] **Step 1: 加运行依赖**

把 `requirements.txt` 末尾加一行：

```
ixbrowser-local-api
```

- [ ] **Step 2: 新建开发依赖文件**

`requirements-dev.txt`：

```
pytest>=8.0
```

- [ ] **Step 3: 安装依赖**

Run:
```bash
pip install -r requirements.txt -r requirements-dev.txt
```
Expected: 成功安装 `ixbrowser-local-api` 与 `pytest`（无报错）。

- [ ] **Step 4: 新建 conftest 让测试能 import 项目根模块**

`tests/conftest.py`：

```python
import os
import sys

# 让 tests/ 下的用例能 import 项目根的 config / common / ...
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

- [ ] **Step 5: 验证 pytest 能收集（暂无用例）**

Run:
```bash
python -m pytest tests/ -q
```
Expected: `no tests ran`（不报 import / 收集错误）。

- [ ] **Step 6: Commit**

```bash
git add requirements.txt requirements-dev.txt tests/conftest.py
git commit -m "build: 引入 ixbrowser-local-api 与 pytest 测试基建"
```

---

## Task 2: BrowserProvider 抽象基类 + 工厂

**Files:**
- Create: `common/browser_provider.py`
- Test: `tests/test_browser_provider.py`

- [ ] **Step 1: 写失败测试**

`tests/test_browser_provider.py`：

```python
import pytest
from common.browser_provider import BrowserProvider


def test_browser_provider_is_abstract():
    # 抽象基类不能直接实例化
    with pytest.raises(TypeError):
        BrowserProvider()


def test_factory_returns_browser_provider():
    from common.browser_provider import get_browser_provider
    p = get_browser_provider()
    assert isinstance(p, BrowserProvider)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_browser_provider.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'common.browser_provider'`

- [ ] **Step 3: 写抽象基类与工厂**

`common/browser_provider.py`：

```python
# -*- coding: utf-8 -*-
"""
common/browser_provider.py — 指纹浏览器窗口抽象契约 + 工厂。

方法名与返回形状对齐历史 BitBrowser 封装，便于上层零改造迁移：
    p = get_browser_provider()
    pid = p.create_browser(name="chatgpt_xxx")
    data = p.open_browser(pid)          # {"ws": ..., "http": ...}
    p.close_browser(pid); p.delete_browser(pid)
"""

from abc import ABC, abstractmethod


class BrowserProvider(ABC):
    @abstractmethod
    def create_browser(self, name="reg", proxy_str=None, **kwargs):
        """创建窗口，返回 profile_id。proxy_str 为空=直连。"""

    @abstractmethod
    def open_browser(self, profile_id):
        """打开窗口，返回 {"ws": <cdp ws/http endpoint>, "http": <debug addr>}。"""

    @abstractmethod
    def close_browser(self, profile_id):
        """关闭窗口（吞异常）。"""

    @abstractmethod
    def delete_browser(self, profile_id):
        """删除窗口配置（吞异常）。"""

    @abstractmethod
    def cleanup_browsers(self, keep=0):
        """删除窗口释放配额，保留最新 keep 个，返回删除数。"""

    @abstractmethod
    def list_browsers(self, page=0, page_size=100):
        """返回 {"data": {"list": [{"id","name","remark","seq"}, ...]}}。"""

    @abstractmethod
    def select_browser(self):
        """交互式选择或新建窗口，返回 profile_id。"""


_PROVIDER = None


def get_browser_provider():
    """返回全局单例 provider（当前固定 ixBrowser）。"""
    global _PROVIDER
    if _PROVIDER is None:
        from common.ixbrowser_provider import IXBrowserProvider
        _PROVIDER = IXBrowserProvider()
    return _PROVIDER
```

> 注意：`get_browser_provider()` 依赖 Task 3 的 `IXBrowserProvider`。Task 2 的
> `test_factory_returns_browser_provider` 会先失败（import 不到实现），属预期；它在
> Task 3 完成后转绿。本步骤先只让 `test_browser_provider_is_abstract` 通过。

- [ ] **Step 4: 运行抽象类测试**

Run: `python -m pytest tests/test_browser_provider.py::test_browser_provider_is_abstract -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add common/browser_provider.py tests/test_browser_provider.py
git commit -m "feat: 新增 BrowserProvider 抽象契约与工厂"
```

---

## Task 3: IXBrowserProvider 实现

**Files:**
- Create: `common/ixbrowser_provider.py`
- Modify: `config.py`（加 ixBrowser 配置，见 Step 1）
- Test: `tests/test_ixbrowser_provider.py`

- [ ] **Step 1: 在 config.py 增加 ixBrowser 配置**

打开 `config.py`，把这段（约 43-45 行）：

```python
# ---------------------------------------------------------------- 本地基建
# BitBrowser 本地 API 地址
BITBROWSER_API = _env("BITBROWSER_API", "http://127.0.0.1:54345")
```

替换为：

```python
# ---------------------------------------------------------------- 本地基建
# ixBrowser 本地 API（IXBrowserClient 默认 127.0.0.1:53200）
IXBROWSER_TARGET = _env("IXBROWSER_TARGET", "127.0.0.1")
IXBROWSER_PORT = int(_env("IXBROWSER_PORT", "53200"))
```

- [ ] **Step 2: 写失败测试**

`tests/test_ixbrowser_provider.py`：

```python
from unittest.mock import MagicMock

from common.ixbrowser_provider import IXBrowserProvider
from common.browser_provider import BrowserProvider


def _provider_with_fake_client():
    p = IXBrowserProvider()
    fake = MagicMock()
    p._client = fake          # 注入 fake，绕过真实 IXBrowserClient
    return p, fake


def test_is_browser_provider():
    assert isinstance(IXBrowserProvider(), BrowserProvider)


def test_parse_proxy_userpass_default_http():
    assert IXBrowserProvider._parse_proxy("u:p@1.2.3.4:8080") == {
        "type": "http", "username": "u", "password": "p",
        "host": "1.2.3.4", "port": "8080",
    }


def test_parse_proxy_socks5_prefix():
    r = IXBrowserProvider._parse_proxy("socks5://u:p@1.2.3.4:1080")
    assert r["type"] == "socks5" and r["host"] == "1.2.3.4" and r["port"] == "1080"


def test_parse_proxy_host_port_only():
    assert IXBrowserProvider._parse_proxy("1.2.3.4:8080") == {
        "type": "http", "host": "1.2.3.4", "port": "8080",
    }


def test_parse_proxy_invalid_returns_none():
    assert IXBrowserProvider._parse_proxy("garbage") is None


def test_create_browser_sets_kernel_130_and_returns_id():
    p, fake = _provider_with_fake_client()
    fake.create_profile.return_value = {"profile_id": 123}
    pid = p.create_browser(name="t")
    assert pid == 123
    profile = fake.create_profile.call_args[0][0]
    assert profile.fingerprint_config.kernel_version == "130"


def test_create_browser_with_proxy_sets_custom_mode():
    p, fake = _provider_with_fake_client()
    fake.create_profile.return_value = {"profile_id": 9}
    p.create_browser(name="t", proxy_str="u:p@1.2.3.4:8080")
    profile = fake.create_profile.call_args[0][0]
    assert profile.proxy_config.proxy_ip == "1.2.3.4"
    assert profile.proxy_config.proxy_port == "8080"


def test_open_browser_maps_ws_and_http():
    p, fake = _provider_with_fake_client()
    fake.open_profile.return_value = {
        "ws": "ws://127.0.0.1:5/devtools/browser/abc",
        "debugging_address": "127.0.0.1:5",
    }
    data = p.open_browser(7)
    assert data == {"ws": "ws://127.0.0.1:5/devtools/browser/abc", "http": "127.0.0.1:5"}


def test_open_browser_falls_back_to_http_endpoint_when_no_ws():
    p, fake = _provider_with_fake_client()
    fake.open_profile.return_value = {"ws": "", "debugging_address": "127.0.0.1:6"}
    data = p.open_browser(7)
    # ws 缺失时用 http endpoint 兜底，供 connect_over_cdp 自动发现
    assert data["ws"] == "http://127.0.0.1:6"


def test_call_raises_on_none_with_client_message():
    p, fake = _provider_with_fake_client()
    fake.create_profile.return_value = None
    fake.message = "boom"
    fake.code = -1
    import pytest
    with pytest.raises(Exception):
        p.create_browser(name="t")


def test_list_browsers_converts_fields():
    p, fake = _provider_with_fake_client()
    fake.get_profile_list.return_value = [
        {"profile_id": 2, "name": "a", "note": "n2"},
        {"profile_id": 1, "name": "b", "note": "n1"},
    ]
    out = p.list_browsers()
    rows = out["data"]["list"]
    assert {"id", "name", "remark", "seq"} <= set(rows[0].keys())
    assert rows[0]["id"] == 2 and rows[0]["seq"] == 2
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_ixbrowser_provider.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'common.ixbrowser_provider'`

- [ ] **Step 4: 写实现**

`common/ixbrowser_provider.py`：

```python
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
```

- [ ] **Step 5: 运行 provider 与工厂测试**

Run:
```bash
python -m pytest tests/test_ixbrowser_provider.py tests/test_browser_provider.py -v
```
Expected: 全部 PASS（含 Task 2 里此前会失败的 `test_factory_returns_browser_provider`）。

- [ ] **Step 6: Commit**

```bash
git add common/ixbrowser_provider.py config.py tests/test_ixbrowser_provider.py
git commit -m "feat: 实现 IXBrowserProvider（ixbrowser-local-api）+ config 切换"
```

---

## Task 4: common/browser.py 切换到 provider

**Files:**
- Modify: `common/browser.py`（import 段约 22-25 行；`open_and_connect` 约 169 行；`create_browser_with_retry` 约 145-162 行）

- [ ] **Step 1: 改 import**

把 `common/browser.py` 顶部这段：

```python
import os
import sys as _sys
_sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bitbrowser import BitBrowser
```

替换为：

```python
import os
import sys as _sys
_sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.browser_provider import get_browser_provider
```

- [ ] **Step 2: 改实例化**

把 `create_browser_with_retry` 与 `open_and_connect` 中的 `bb = BitBrowser()`（约 169 行）改为：

```python
    bb = get_browser_provider()
```

`create_browser_with_retry(bb, name)` 内部 `bb.create_browser(name=name)` 调用不变（provider 接口兼容）。

- [ ] **Step 3: 验证无残留 + 可导入**

Run:
```bash
grep -n "BitBrowser" common/browser.py || echo "clean"
python -c "import common.browser; print('import ok')"
```
Expected: 第一条输出 `clean`；第二条输出 `import ok`（需已 `pip install ixbrowser-local-api`）。

- [ ] **Step 4: Commit**

```bash
git add common/browser.py
git commit -m "refactor: common/browser 改用 get_browser_provider"
```

---

## Task 5: register.py 切换

**Files:**
- Modify: `register.py`（import 约 27 行；实例化约 155 / 3220 / 3947 行）

- [ ] **Step 1: 改 import**

把 `register.py:27` 的：

```python
from bitbrowser import BitBrowser
```

替换为：

```python
from common.browser_provider import get_browser_provider
```

- [ ] **Step 2: 改全部实例化**

把 `register.py` 中所有 `bb = BitBrowser()`（约 155、3220、3947 行）替换为：

```python
    bb = get_browser_provider()
```

- [ ] **Step 3: 验证无残留 + 可导入**

Run:
```bash
grep -n "BitBrowser" register.py || echo "clean"
python -c "import register; print('import ok')"
```
Expected: `clean` 与 `import ok`。

- [ ] **Step 4: Commit**

```bash
git add register.py
git commit -m "refactor: register.py 改用 get_browser_provider"
```

---

## Task 6: register_grok.py 切换

**Files:**
- Modify: `register_grok.py`（import 约 31 行；实例化约 457 / 520 行）

- [ ] **Step 1: 改 import**

把 `register_grok.py:31` 的：

```python
from bitbrowser import BitBrowser
```

替换为：

```python
from common.browser_provider import get_browser_provider
```

- [ ] **Step 2: 改全部实例化**

把 `register_grok.py` 中所有 `bb = BitBrowser()`（约 457、520 行）替换为：

```python
    bb = get_browser_provider()
```

- [ ] **Step 3: 验证无残留 + 可导入**

Run:
```bash
grep -n "BitBrowser" register_grok.py || echo "clean"
python -c "import register_grok; print('import ok')"
```
Expected: `clean` 与 `import ok`。

- [ ] **Step 4: Commit**

```bash
git add register_grok.py
git commit -m "refactor: register_grok.py 改用 get_browser_provider"
```

---

## Task 7: register_outlook_standalone.py 删重复封装

**Files:**
- Modify: `register_outlook_standalone.py`（删类约 99-232 行；`_parse_proxy` 静态调用约 1431 / 1443 行；实例化约 1973 行；import 段）

- [ ] **Step 1: 确认所有 BitBrowserClient 引用点**

Run:
```bash
grep -n "BitBrowserClient" register_outlook_standalone.py
```
Expected: 列出类定义（约 101 行 `class BitBrowserClient:`）、`BitBrowserClient._parse_proxy(...)`（约 1431、1443）、`bb = BitBrowserClient()`（约 1973）。记下全部行号。

- [ ] **Step 2: 加 provider import**

在该文件已有 import 区（例如 `from config import ...` 附近）加入：

```python
from common.browser_provider import get_browser_provider
from common.ixbrowser_provider import IXBrowserProvider
```

- [ ] **Step 3: 删除整个 `class BitBrowserClient`**

删掉从 `# ======================== BitBrowser API ========================`
到该类结束（`_parse_proxy` 的 `return None` 之后、`# ======================== Helper Functions`
之前）的全部内容，即原约 99-233 行。保留下方的 `# ===== Helper Functions =====` 段。

- [ ] **Step 4: 替换实例化**

把 `bb = BitBrowserClient()`（约 1973 行）替换为：

```python
    bb = get_browser_provider()
```

- [ ] **Step 5: 替换静态 _parse_proxy 调用**

把约 1431、1443 行的 `BitBrowserClient._parse_proxy(proxy_str)` 替换为：

```python
    p = IXBrowserProvider._parse_proxy(proxy_str)
```

（保持等号左侧变量名与原行一致，仅改右侧类名。）

- [ ] **Step 6: 验证无残留 + 可导入**

Run:
```bash
grep -n "BitBrowserClient\|from bitbrowser\|BITBROWSER_API" register_outlook_standalone.py || echo "clean"
python -c "import register_outlook_standalone; print('import ok')"
```
Expected: `clean` 与 `import ok`。

- [ ] **Step 7: Commit**

```bash
git add register_outlook_standalone.py
git commit -m "refactor: register_outlook_standalone 删除重复 BitBrowser 封装，改用 provider"
```

---

## Task 8: outlook_reg_loop.py 切换

**Files:**
- Modify: `outlook_reg_loop.py`（`bb = mod.BitBrowserClient()` 约 253 行；import 段约 22-30 行）

- [ ] **Step 1: 加 provider import**

在 `outlook_reg_loop.py` 顶部 import 区（约 30 行后）加入：

```python
from common.browser_provider import get_browser_provider
```

- [ ] **Step 2: 改 bb 来源**

把 `outlook_reg_loop.py:253` 的：

```python
    bb = mod.BitBrowserClient()
```

替换为：

```python
    bb = get_browser_provider()
```

（`mod` 仍用于其它 outlook 注册函数，保留；仅浏览器实例改为 provider。）

- [ ] **Step 3: 验证无残留 + 可导入**

Run:
```bash
grep -n "BitBrowserClient" outlook_reg_loop.py || echo "clean"
python -c "import outlook_reg_loop; print('import ok')"
```
Expected: `clean` 与 `import ok`。

- [ ] **Step 4: Commit**

```bash
git add outlook_reg_loop.py
git commit -m "refactor: outlook_reg_loop 改用 get_browser_provider"
```

---

## Task 9: mailbox_broker.py 切换

**Files:**
- Modify: `mailbox_broker.py`（import 约 34 行；实例化约 111 行）

- [ ] **Step 1: 改 import**

把 `mailbox_broker.py:34` 的：

```python
from bitbrowser import BitBrowser
```

替换为：

```python
from common.browser_provider import get_browser_provider
```

- [ ] **Step 2: 改实例化**

把 `mailbox_broker.py:111` 的 `self.bb = BitBrowser()` 替换为：

```python
        self.bb = get_browser_provider()
```

- [ ] **Step 3: 验证无残留 + 可导入**

Run:
```bash
grep -n "BitBrowser" mailbox_broker.py || echo "clean"
python -c "import mailbox_broker; print('import ok')"
```
Expected: `clean` 与 `import ok`。

- [ ] **Step 4: Commit**

```bash
git add mailbox_broker.py
git commit -m "refactor: mailbox_broker 改用 get_browser_provider"
```

---

## Task 10: validate_keys.py 切换

**Files:**
- Modify: `validate_keys.py`（import 约 15 行；实例化约 135 行）

- [ ] **Step 1: 改 import**

把 `validate_keys.py:15` 的：

```python
from bitbrowser import BitBrowser
```

替换为：

```python
from common.browser_provider import get_browser_provider
```

- [ ] **Step 2: 改实例化**

把 `validate_keys.py:135` 的 `bb = BitBrowser()` 替换为：

```python
    bb = get_browser_provider()
```

- [ ] **Step 3: 验证无残留 + 可导入**

Run:
```bash
grep -n "BitBrowser" validate_keys.py || echo "clean"
python -c "import validate_keys; print('import ok')"
```
Expected: `clean` 与 `import ok`。

- [ ] **Step 4: Commit**

```bash
git add validate_keys.py
git commit -m "refactor: validate_keys 改用 get_browser_provider"
```

---

## Task 11: 删除 bitbrowser.py + 文档/模板清理

**Files:**
- Delete: `bitbrowser.py`
- Modify: `.env.example`（约 16-17 行）
- Modify: `README.md`（前置条件 BitBrowser 段、安装段、配置表 `BITBROWSER_API` 行、运行段提示）

- [ ] **Step 1: 删除 bitbrowser.py**

Run:
```bash
git rm bitbrowser.py
```

- [ ] **Step 2: 改 .env.example**

把 `.env.example` 的：

```
# ---------------- BitBrowser 本地 API ----------------
BITBROWSER_API=http://127.0.0.1:54345
```

替换为：

```
# ---------------- ixBrowser 本地 API ----------------
# 需先启动 ixBrowser 客户端；本地 API 默认 127.0.0.1:53200
IXBROWSER_TARGET=127.0.0.1
IXBROWSER_PORT=53200
```

- [ ] **Step 3: 改 README.md（BitBrowser → ixBrowser）**

在 `README.md` 中按语义替换以下处（用 grep 定位，逐处改）：

Run 先定位：
```bash
grep -n "BitBrowser\|比特浏览器\|BITBROWSER_API\|54345" README.md
```

逐处改写要点：
- 「前置条件 ① 比特浏览器 BitBrowser」整段 → 「ixBrowser 指纹浏览器」：安装并启动 ixBrowser 客户端，确保本地 API 在线（默认 `127.0.0.1:53200`）。
- 安装段不再需要 BitBrowser 客户端说明；`pip install -r requirements.txt` 会带上 `ixbrowser-local-api`。
- 配置表里 `BITBROWSER_API` 行 → `IXBROWSER_TARGET`（默认 `127.0.0.1`）/ `IXBROWSER_PORT`（默认 `53200`）。
- 运行段中 `前置：BitBrowser(54345) 在线` 提示 → `前置：ixBrowser(53200) 在线`。
- 顶部 badge `BitBrowser-指纹隔离` → `ixBrowser-指纹隔离`（可选）。

- [ ] **Step 4: 同步 run_full_flow.py 注释**

`run_full_flow.py:13` 的注释 `前置：BitBrowser(54345) 在线...` 改为：

```python
前置：ixBrowser(53200) 在线、Clash Verge(控制器 9097 / 混合端口 7897) 在线。
```

- [ ] **Step 5: 全仓残留扫描**

Run:
```bash
grep -rn "from bitbrowser\|import bitbrowser\|BitBrowser\|BitBrowserClient\|BITBROWSER_API\|54345" \
  --include=*.py --include=*.md --include=.env.example . || echo "ALL CLEAN"
```
Expected: `ALL CLEAN`（README 里若保留历史 CHANGELOG 提及可豁免，但代码/配置必须干净）。

- [ ] **Step 6: 跑全部单测**

Run:
```bash
python -m pytest tests/ -v
```
Expected: 全部 PASS。

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: 删除 bitbrowser.py，文档/模板切换到 ixBrowser"
```

---

## Task 12: 人工端到端验收（需本机 ixBrowser 在线）

> 这步无法在无 ixBrowser 客户端的环境自动完成，由操作者本机执行。

**Files:** 无（运行验证）

- [ ] **Step 1: 确认 ixBrowser 客户端已启动**，本地 API 监听 `127.0.0.1:53200`。

- [ ] **Step 2: provider 连通性自测**

Run:
```bash
python -c "from common.browser_provider import get_browser_provider as g; print(g().list_browsers())"
```
Expected: 打印 `{'data': {'list': [...]}}`（不抛连接错误）。

- [ ] **Step 3: 单条链路端到端（建议 chatgpt 或 claude）**

Run（dry-run 先确认命令链路）：
```bash
python run_full_flow.py --platforms chatgpt --dry-run
```
然后实跑一个：
```bash
python run_full_flow.py --skip-email --email <你的测试号> --password <pwd> --platforms chatgpt
```
Expected: ixBrowser 建窗口 → Playwright 经 `connect_over_cdp` 连上 → 注入 stealth → 打开目标站 → 流程结束后窗口被关闭并删除。

- [ ] **Step 4: outlook per-window 代理验收**

在 `.env` 配置 `OUTLOOK_PROXIES`，Run:
```bash
python outlook_reg_loop.py --count 1
```
Expected: 新窗口出口 IP = 配置的住宅代理 IP（窗口内访问 IP 查询站确认）。

- [ ] **Step 5: 若 ws 连接失败的兜底排查**

若 `connect_over_cdp` 报错：用
```bash
python -c "from common.browser_provider import get_browser_provider as g; p=g(); pid=p.create_browser(name='t'); print(p.open_browser(pid)); p.close_browser(pid); p.delete_browser(pid)"
```
查看 `open_browser` 返回的 `ws`/`http` 实际值，据此校准 `IXBrowserProvider.open_browser`
的 endpoint 选择（参见设计文档风险 1）。

---

## 完成标准（对照 spec §6 验收）

- [ ] `bitbrowser.py` 删除；全仓无 `from bitbrowser` / `BitBrowser` / `BITBROWSER_API` 残留。
- [ ] 7 个调用文件 + config/.env.example/requirements/README 全部改完。
- [ ] `register_outlook_standalone.py` 无独立浏览器封装类。
- [ ] `python -m pytest tests/` 全绿。
- [ ] 本机 ixBrowser 在线时，单条链路端到端跑通；outlook per-window 代理生效。
