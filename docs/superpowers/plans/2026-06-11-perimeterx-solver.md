# PerimeterX 长按逆向求解器 — Phase 0–1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建好 PerimeterX 长按逆向的「侦查 + 反混淆」地基——抓取工具链、配对样本语料库、协议图、载荷 schema 与解密器，让后续 Phase 2 伪造从盲打变靶向。

**Architecture:** 新建顶层包 `perimeterx_solver/`，分 `recon/`（Phase 0 侦查）与 `analysis/`（Phase 1 反混淆）两层。纯逻辑组件走 TDD 单测；触活体 PerimeterX 的实弹任务带验收标准（非单测），部分需真人手动长按参与。设计模式落实到具体类（Repository/Memento/Strategy/Template Method/Facade）。

**Tech Stack:** Python 3.13、pytest（prepend 模式，`tests/conftest.py` 已加项目根到 sys.path）、Playwright/CDP（插桩用 vanilla Chromium）、现有 `common.browser_provider`/ixBrowser（对照同环境用）。参考 `_funcaptcha_solver/`（Arkose 同款范式）。

**测试约定（务必遵守，踩过的坑）：**
- **禁止**新建 `tests/__init__.py`、`tests/perimeterx_solver/__init__.py`、`pytest.ini`、根 `conftest.py`（会破坏 services/tests 收集）。
- 源包 `perimeterx_solver/__init__.py` 必须有（与 `outlook_hybrid/` 一致）。
- 异步用例用 `asyncio.run()` 包装，**不**加 pytest-asyncio marker。
- 全量 `python -m pytest -q` 基线 = 19 个既有失败（services 异步 DB 隔离，与本工程无关）；新任务**不得**让该数字变大。
- 每个任务跑完用 `python -m pytest tests/perimeterx_solver -q` 验证本包，再确认全量未回归。

**任务类型标记：**
- 🟢 **TDD**：纯逻辑，先写失败测试 → 实现 → 通过 → 提交。
- 🔴 **实弹/交互**：跑活体 PerimeterX，带验收标准，非单测；标 ⚠️ 的需真人手动长按，不能由 subagent 自动完成。

---

## 文件结构

```
perimeterx_solver/
  __init__.py                      # 包标记 + 版本
  models.py                        # 数据类：CapturedRequest / CookieSnapshot / Sample / TracedPayload / CryptoFinding
  classify.py                      # PX 域识别 + collector 载荷解析（纯逻辑）
  corpus.py                        # SampleCorpus (Repository)
  recon/
    __init__.py
    traffic_recorder.py            # PxTrafficRecorder（CDP 网络抓取，包住 classify）
    script_dumper.py               # PxScriptDumper（脚本原文+hash+版本）
    cookie_snapshotter.py          # PxCookieSnapshotter (Memento)
    harness.py                     # ReconHarness (Template Method) + BotRun/HumanRun
  analysis/
    __init__.py
    hook_injector.py               # HookInjector (Strategy 四族 JS 片段)
    instrumented_session.py        # PxInstrumentedSession (Facade)
    payload_tracer.py              # PayloadTracer（明文→加密→出口 关联）
    crypto_locator.py              # CryptoLocator（定位加密原语）
    decryptor.py                   # PayloadDecryptor (Strategy)（算法在 Task 13 后填）
    schema_differ.py               # SchemaDiffer（真人 vs 机器 明文 diff）
  corpus/                          # 运行期样本落地（git 忽略大 body，留索引）
_recon_perimeterx.py               # 🔴 Phase 0 实弹入口（手动跑）
_instrument_perimeterx.py          # 🔴 Phase 1 实弹入口（手动跑）
tests/perimeterx_solver/           # 单测（无 __init__.py）
  test_classify.py
  test_corpus.py
  test_script_dumper.py
  test_cookie_snapshotter.py
  test_harness.py
  test_hook_injector.py
  test_payload_tracer.py
  test_crypto_locator.py
  test_decryptor.py
  test_schema_differ.py
docs/superpowers/research/
  perimeterx-protocol-map.md       # 🔴 Phase 0 产出
  perimeterx-payload-schema.md     # 🔴 Phase 1 产出
  perimeterx-crypto-spec.md        # 🔴 Phase 1 产出
  perimeterx-diff-report.md        # 🔴 Phase 1 产出
```

---

# Phase 0：侦查 & 协议图

## Task 1: 包骨架 + 数据模型 🟢

**Files:**
- Create: `perimeterx_solver/__init__.py`
- Create: `perimeterx_solver/models.py`
- Test: `tests/perimeterx_solver/test_models.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/perimeterx_solver/test_models.py
from perimeterx_solver.models import CapturedRequest, CookieSnapshot, Sample


def test_captured_request_roundtrip():
    r = CapturedRequest(url="https://PXzC5j78di.px-cdn.net/api/v2/collector",
                        method="POST", req_body="payload=abc&appId=PXzC5j78di",
                        resp_status=200, resp_body="{}", req_headers={}, resp_headers={}, ts=1.0)
    d = r.to_dict()
    assert d["url"].endswith("/api/v2/collector")
    assert CapturedRequest.from_dict(d).method == "POST"


def test_sample_outcome_validation():
    s = Sample(run_id="r1", outcome="pass")
    assert s.outcome == "pass"
    assert s.requests == [] and s.cookie_snapshots == []
    import pytest
    with pytest.raises(ValueError):
        Sample(run_id="r2", outcome="bogus")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/perimeterx_solver/test_models.py -q`
Expected: FAIL（ModuleNotFoundError: perimeterx_solver）

- [ ] **Step 3: 写实现**

```python
# perimeterx_solver/__init__.py
"""PerimeterX 长按逆向求解器（Phase 0-1：侦查 + 反混淆地基）。"""
__version__ = "0.0.1"
```

```python
# perimeterx_solver/models.py
from dataclasses import dataclass, field, asdict


@dataclass
class CapturedRequest:
    url: str
    method: str
    req_body: str = ""
    resp_status: int = 0
    resp_body: str = ""
    req_headers: dict = field(default_factory=dict)
    resp_headers: dict = field(default_factory=dict)
    ts: float = 0.0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


@dataclass
class CookieSnapshot:
    label: str
    ts: float
    cookies: dict = field(default_factory=dict)  # name -> value

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


_VALID_OUTCOMES = ("pass", "fail")


@dataclass
class Sample:
    run_id: str
    outcome: str  # "pass" | "fail"
    captured_at: float = 0.0
    requests: list = field(default_factory=list)        # list[CapturedRequest]
    cookie_snapshots: list = field(default_factory=list)  # list[CookieSnapshot]
    script_refs: list = field(default_factory=list)      # list[dict] {url, sha256, path}
    pointer_stream: list = field(default_factory=list)   # list[dict] {x,y,t,type}（仅真人采集）
    meta: dict = field(default_factory=dict)             # proxy/app_id/ua/...

    def __post_init__(self):
        if self.outcome not in _VALID_OUTCOMES:
            raise ValueError(f"outcome must be one of {_VALID_OUTCOMES}, got {self.outcome!r}")

    def to_dict(self):
        d = asdict(self)
        d["requests"] = [r.to_dict() if isinstance(r, CapturedRequest) else r for r in self.requests]
        d["cookie_snapshots"] = [c.to_dict() if isinstance(c, CookieSnapshot) else c for c in self.cookie_snapshots]
        return d

    @classmethod
    def from_dict(cls, d):
        s = cls(run_id=d["run_id"], outcome=d["outcome"], captured_at=d.get("captured_at", 0.0),
                script_refs=d.get("script_refs", []), pointer_stream=d.get("pointer_stream", []),
                meta=d.get("meta", {}))
        s.requests = [CapturedRequest.from_dict(x) for x in d.get("requests", [])]
        s.cookie_snapshots = [CookieSnapshot.from_dict(x) for x in d.get("cookie_snapshots", [])]
        return s
```

定义 `TracedPayload` / `CryptoFinding` 留到 Task 11/12（用到时再加，避免未用类型）。

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/perimeterx_solver/test_models.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add perimeterx_solver/__init__.py perimeterx_solver/models.py tests/perimeterx_solver/test_models.py
git commit -m "feat(px): 包骨架 + 数据模型(CapturedRequest/CookieSnapshot/Sample)"
```

---

## Task 2: PX 域识别 + collector 载荷解析 🟢

**Files:**
- Create: `perimeterx_solver/classify.py`
- Test: `tests/perimeterx_solver/test_classify.py`

**背景**：collector POST body 是 form 编码 `payload=<加密base64>&appId=..&tag=..&uuid=..&ft=..&pxhd=..`（实弹会确认；解析器对 form 与 JSON 都兼容）。

- [ ] **Step 1: 写失败测试**

```python
# tests/perimeterx_solver/test_classify.py
from perimeterx_solver.classify import is_px_url, classify_px_url, parse_collector_body, PxKind


def test_is_px_url():
    assert is_px_url("https://PXzC5j78di.px-cdn.net/api/v2/collector")
    assert is_px_url("https://collector-PXzC5j78di.px-cloud.net/api/v1/collector")
    assert is_px_url("https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di")
    assert not is_px_url("https://signup.live.com/API/CreateAccount")


def test_classify_px_url():
    assert classify_px_url("https://PXzC5j78di.px-cdn.net/api/v2/collector", "POST") == PxKind.COLLECTOR
    assert classify_px_url("https://client.px-cloud.net/PXzC5j78di/main.min.js", "GET") == PxKind.SCRIPT
    assert classify_px_url("https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di", "GET") == PxKind.CHALLENGE_IFRAME
    assert classify_px_url("https://x.px-cdn.net/favicon.ico", "GET") == PxKind.OTHER


def test_parse_collector_form_body():
    body = "payload=ZW5jcnlwdGVk&appId=PXzC5j78di&tag=mobile&uuid=u-1&ft=2&pxhd=hd-1"
    p = parse_collector_body(body)
    assert p.encrypted_blob == "ZW5jcnlwdGVk"
    assert p.plaintext_fields["appId"] == "PXzC5j78di"
    assert p.plaintext_fields["uuid"] == "u-1"


def test_parse_collector_json_body():
    body = '{"payload":"ZW5j","appId":"PXzC5j78di","uuid":"u-2"}'
    p = parse_collector_body(body)
    assert p.encrypted_blob == "ZW5j"
    assert p.plaintext_fields["uuid"] == "u-2"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/perimeterx_solver/test_classify.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

```python
# perimeterx_solver/classify.py
import json
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse, parse_qs

_PX_HOST_SUFFIXES = (".px-cdn.net", ".px-cloud.net", "hsprotect.net", ".pxchk.net")
_PX_HOST_CONTAINS = ("px-cloud.net", "px-cdn.net")


class PxKind(str, Enum):
    COLLECTOR = "collector"
    SCRIPT = "script"
    CHALLENGE_IFRAME = "challenge_iframe"
    OTHER = "other"


def is_px_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    return host.endswith(_PX_HOST_SUFFIXES) or any(s in host for s in _PX_HOST_CONTAINS)


def classify_px_url(url: str, method: str) -> PxKind:
    if not is_px_url(url):
        return PxKind.OTHER
    path = (urlparse(url).path or "").lower()
    host = (urlparse(url).hostname or "").lower()
    if "/collector" in path and method.upper() == "POST":
        return PxKind.COLLECTOR
    if path.endswith(".js"):
        return PxKind.SCRIPT
    if "hsprotect.net" in host:
        return PxKind.CHALLENGE_IFRAME
    return PxKind.OTHER


@dataclass
class CollectorPayload:
    encrypted_blob: str = ""
    plaintext_fields: dict = field(default_factory=dict)
    raw: str = ""


def parse_collector_body(body: str) -> CollectorPayload:
    raw = body or ""
    # 先试 JSON
    stripped = raw.strip()
    if stripped.startswith("{"):
        try:
            d = json.loads(stripped)
            blob = str(d.pop("payload", "")) if "payload" in d else ""
            return CollectorPayload(encrypted_blob=blob, plaintext_fields={k: v for k, v in d.items()}, raw=raw)
        except Exception:
            pass
    # 再试 form 编码
    qs = parse_qs(raw, keep_blank_values=True)
    flat = {k: v[0] if v else "" for k, v in qs.items()}
    blob = flat.pop("payload", "")
    return CollectorPayload(encrypted_blob=blob, plaintext_fields=flat, raw=raw)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/perimeterx_solver/test_classify.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add perimeterx_solver/classify.py tests/perimeterx_solver/test_classify.py
git commit -m "feat(px): PX 域识别 + collector 载荷解析(form/json)"
```

---

## Task 3: SampleCorpus (Repository) 🟢

**Files:**
- Create: `perimeterx_solver/corpus.py`
- Test: `tests/perimeterx_solver/test_corpus.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/perimeterx_solver/test_corpus.py
from perimeterx_solver.corpus import SampleCorpus
from perimeterx_solver.models import Sample, CapturedRequest


def test_save_load_roundtrip(tmp_path):
    c = SampleCorpus(root=str(tmp_path))
    s = Sample(run_id="r1", outcome="fail")
    s.requests.append(CapturedRequest(url="u", method="POST"))
    c.save(s)
    loaded = c.load("r1")
    assert loaded.outcome == "fail"
    assert loaded.requests[0].url == "u"


def test_list_and_golden(tmp_path):
    c = SampleCorpus(root=str(tmp_path))
    c.save(Sample(run_id="f1", outcome="fail"))
    c.save(Sample(run_id="p1", outcome="pass"))
    assert {s.run_id for s in c.list()} == {"f1", "p1"}
    assert {s.run_id for s in c.list(outcome="fail")} == {"f1"}
    assert c.golden().run_id == "p1"


def test_golden_none_when_no_pass(tmp_path):
    c = SampleCorpus(root=str(tmp_path))
    c.save(Sample(run_id="f1", outcome="fail"))
    assert c.golden() is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/perimeterx_solver/test_corpus.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

```python
# perimeterx_solver/corpus.py
import json
import os

from .models import Sample


class SampleCorpus:
    """配对样本仓库（Repository）：按 outcome/run_id 落地与索引。

    布局：<root>/<outcome>/<run_id>/sample.json
    """

    def __init__(self, root="perimeterx_solver/corpus"):
        self.root = root

    def _dir(self, outcome, run_id):
        return os.path.join(self.root, outcome, run_id)

    def save(self, sample: Sample):
        d = self._dir(sample.outcome, sample.run_id)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "sample.json"), "w", encoding="utf-8") as f:
            json.dump(sample.to_dict(), f, ensure_ascii=False, indent=2)

    def load(self, run_id) -> Sample:
        for outcome in ("pass", "fail"):
            p = os.path.join(self._dir(outcome, run_id), "sample.json")
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    return Sample.from_dict(json.load(f))
        raise FileNotFoundError(run_id)

    def list(self, outcome=None):
        outcomes = (outcome,) if outcome else ("pass", "fail")
        out = []
        for oc in outcomes:
            base = os.path.join(self.root, oc)
            if not os.path.isdir(base):
                continue
            for rid in sorted(os.listdir(base)):
                p = os.path.join(base, rid, "sample.json")
                if os.path.exists(p):
                    with open(p, encoding="utf-8") as f:
                        out.append(Sample.from_dict(json.load(f)))
        return out

    def golden(self):
        passes = self.list(outcome="pass")
        return passes[0] if passes else None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/perimeterx_solver/test_corpus.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add perimeterx_solver/corpus.py tests/perimeterx_solver/test_corpus.py
git commit -m "feat(px): SampleCorpus 配对样本仓库(Repository)"
```

---

## Task 4: PxScriptDumper 🟢

**Files:**
- Create: `perimeterx_solver/recon/__init__.py`、`perimeterx_solver/recon/script_dumper.py`
- Test: `tests/perimeterx_solver/test_script_dumper.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/perimeterx_solver/test_script_dumper.py
from perimeterx_solver.recon.script_dumper import PxScriptDumper


def test_dump_hashes_and_stores(tmp_path):
    d = PxScriptDumper(out_dir=str(tmp_path))
    ref = d.dump("https://client.px-cloud.net/PXzC5j78di/main.min.js", "var a=1;")
    assert len(ref["sha256"]) == 64
    assert ref["url"].endswith("main.min.js")
    import os
    assert os.path.exists(ref["path"])


def test_same_content_same_hash(tmp_path):
    d = PxScriptDumper(out_dir=str(tmp_path))
    a = d.dump("u1", "same")
    b = d.dump("u2", "same")
    assert a["sha256"] == b["sha256"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/perimeterx_solver/test_script_dumper.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

```python
# perimeterx_solver/recon/__init__.py
```

```python
# perimeterx_solver/recon/script_dumper.py
import hashlib
import os


class PxScriptDumper:
    """抓 collector/挑战脚本原文 + sha256 + 落盘（应对 VM 轮换：钉死版本）。"""

    def __init__(self, out_dir="perimeterx_solver/corpus/_scripts"):
        self.out_dir = out_dir

    def dump(self, url: str, text: str) -> dict:
        os.makedirs(self.out_dir, exist_ok=True)
        sha = hashlib.sha256((text or "").encode("utf-8", "replace")).hexdigest()
        path = os.path.join(self.out_dir, f"{sha}.js")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(text or "")
        return {"url": url, "sha256": sha, "path": path}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/perimeterx_solver/test_script_dumper.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add perimeterx_solver/recon/__init__.py perimeterx_solver/recon/script_dumper.py tests/perimeterx_solver/test_script_dumper.py
git commit -m "feat(px): PxScriptDumper 脚本原文+hash 落盘"
```

---

## Task 5: PxCookieSnapshotter (Memento) 🟢

**Files:**
- Create: `perimeterx_solver/recon/cookie_snapshotter.py`
- Test: `tests/perimeterx_solver/test_cookie_snapshotter.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/perimeterx_solver/test_cookie_snapshotter.py
from perimeterx_solver.recon.cookie_snapshotter import PxCookieSnapshotter, PX_COOKIE_NAMES, is_px_cookie


def test_is_px_cookie():
    assert is_px_cookie("_px3")
    assert is_px_cookie("_pxhd")
    assert is_px_cookie("_pxff_abc")   # 前缀族
    assert not is_px_cookie("MUID")


def test_snapshot_filters_px_only():
    snap = PxCookieSnapshotter()
    m = snap.snapshot("after_hold", ts=1.0,
                      cookies=[{"name": "_px3", "value": "tok"}, {"name": "MUID", "value": "x"}])
    assert m.label == "after_hold"
    assert m.cookies == {"_px3": "tok"}


def test_diff_detects_new_clearance():
    snap = PxCookieSnapshotter()
    a = snap.snapshot("before", ts=1.0, cookies=[{"name": "_pxhd", "value": "h"}])
    b = snap.snapshot("after", ts=2.0, cookies=[{"name": "_pxhd", "value": "h"}, {"name": "_px3", "value": "t"}])
    assert snap.diff(a, b) == {"_px3": (None, "t")}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/perimeterx_solver/test_cookie_snapshotter.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

```python
# perimeterx_solver/recon/cookie_snapshotter.py
from ..models import CookieSnapshot

PX_COOKIE_NAMES = ("_px3", "_pxhd", "_pxvid", "pxcts")
_PX_COOKIE_PREFIXES = ("_pxff_", "_px")


def is_px_cookie(name: str) -> bool:
    return name in PX_COOKIE_NAMES or any(name.startswith(p) for p in _PX_COOKIE_PREFIXES)


class PxCookieSnapshotter:
    """各生命周期节点快照 PX cookie（Memento）。"""

    def snapshot(self, label: str, ts: float, cookies) -> CookieSnapshot:
        flat = {c["name"]: c["value"] for c in cookies if is_px_cookie(c.get("name", ""))}
        return CookieSnapshot(label=label, ts=ts, cookies=flat)

    @staticmethod
    def diff(a: CookieSnapshot, b: CookieSnapshot) -> dict:
        """返回 {name: (old, new)}，仅含变化项（含新增/删除）。"""
        out = {}
        keys = set(a.cookies) | set(b.cookies)
        for k in keys:
            old = a.cookies.get(k)
            new = b.cookies.get(k)
            if old != new:
                out[k] = (old, new)
        return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/perimeterx_solver/test_cookie_snapshotter.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add perimeterx_solver/recon/cookie_snapshotter.py tests/perimeterx_solver/test_cookie_snapshotter.py
git commit -m "feat(px): PxCookieSnapshotter cookie 快照(Memento)"
```

---

## Task 6: PxTrafficRecorder（围绕 classify 的缓冲/装配）🟢

**Files:**
- Create: `perimeterx_solver/recon/traffic_recorder.py`
- Test: `tests/perimeterx_solver/test_traffic_recorder.py`

**说明**：把「CDP 网络事件」抽象成 `on_request_finished(url, method, req_body, status, resp_body, headers, ts)` 回调；活体 CDP 绑定是 Task 8 的薄适配。本任务只 TDD 缓冲 + PX 过滤 + collector 解析装配。

- [ ] **Step 1: 写失败测试**

```python
# tests/perimeterx_solver/test_traffic_recorder.py
from perimeterx_solver.recon.traffic_recorder import PxTrafficRecorder


def test_records_only_px_and_parses_collector():
    rec = PxTrafficRecorder()
    rec.on_request_finished("https://signup.live.com/x", "GET", "", 200, "", {}, 1.0)  # 丢弃
    rec.on_request_finished("https://PXzC5j78di.px-cdn.net/api/v2/collector", "POST",
                            "payload=ZW5j&appId=PXzC5j78di&uuid=u1", 200, "{}", {}, 2.0)
    assert len(rec.captured) == 1
    cap = rec.captured[0]
    assert cap.url.endswith("/collector")
    # collector 解析结果挂在 recorder 上，供协议图用
    cps = rec.collector_payloads()
    assert cps[0].plaintext_fields["uuid"] == "u1"
    assert cps[0].encrypted_blob == "ZW5j"


def test_collector_payloads_in_order():
    rec = PxTrafficRecorder()
    for i, ts in enumerate((1.0, 2.0)):
        rec.on_request_finished("https://PXzC5j78di.px-cdn.net/api/v2/collector", "POST",
                                f"payload=p{i}&appId=A", 200, "", {}, ts)
    assert [c.encrypted_blob for c in rec.collector_payloads()] == ["p0", "p1"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/perimeterx_solver/test_traffic_recorder.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

```python
# perimeterx_solver/recon/traffic_recorder.py
from ..classify import is_px_url, classify_px_url, parse_collector_body, PxKind
from ..models import CapturedRequest


class PxTrafficRecorder:
    """缓冲 PX 域请求并解析 collector 载荷。活体 CDP 事件经 on_request_finished 注入。"""

    def __init__(self):
        self.captured = []  # list[CapturedRequest]

    def on_request_finished(self, url, method, req_body, status, resp_body, headers, ts):
        if not is_px_url(url):
            return
        self.captured.append(CapturedRequest(
            url=url, method=method, req_body=req_body or "",
            resp_status=status, resp_body=resp_body or "",
            req_headers=dict(headers or {}), resp_headers={}, ts=ts,
        ))

    def collector_payloads(self):
        out = []
        for c in sorted(self.captured, key=lambda r: r.ts):
            if classify_px_url(c.url, c.method) == PxKind.COLLECTOR:
                out.append(parse_collector_body(c.req_body))
        return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/perimeterx_solver/test_traffic_recorder.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add perimeterx_solver/recon/traffic_recorder.py tests/perimeterx_solver/test_traffic_recorder.py
git commit -m "feat(px): PxTrafficRecorder PX流量缓冲+collector解析"
```

---

## Task 7: ReconHarness (Template Method) + HumanPassCapture 落档逻辑 🟢

**Files:**
- Create: `perimeterx_solver/recon/harness.py`
- Test: `tests/perimeterx_solver/test_harness.py`

**说明**：`ReconHarness` 固定骨架（开会话→挂录制→驱动到挑战→收尾存档）；`_drive_to_challenge` 抽象，`BotRun`/`HumanRun` 填充。`HumanRun` 只在 `_px3` 出现（PASS）时落 `outcome="pass"` 黄金档。本任务用假 driver TDD 骨架与落档判定。

- [ ] **Step 1: 写失败测试**

```python
# tests/perimeterx_solver/test_harness.py
from perimeterx_solver.recon.harness import ReconHarness, outcome_from_cookies


def test_outcome_from_cookies():
    assert outcome_from_cookies([{"name": "_px3", "value": "t"}]) == "pass"
    assert outcome_from_cookies([{"name": "_pxhd", "value": "h"}]) == "fail"


def test_harness_template_order(tmp_path):
    calls = []

    class FakeRun(ReconHarness):
        def _open_session(self):
            calls.append("open"); return {"final_cookies": [{"name": "_px3", "value": "t"}]}
        def _drive_to_challenge(self, session):
            calls.append("drive")
        def _collect(self, session):
            calls.append("collect")
            return [], [], [{"name": "_px3", "value": "t"}], []
        def _close_session(self, session):
            calls.append("close")

    from perimeterx_solver.corpus import SampleCorpus
    h = FakeRun(corpus=SampleCorpus(root=str(tmp_path)), run_id="r1", meta={})
    sample = h.run()
    assert calls == ["open", "drive", "collect", "close"]
    assert sample.outcome == "pass"
    assert SampleCorpus(root=str(tmp_path)).golden().run_id == "r1"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/perimeterx_solver/test_harness.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

```python
# perimeterx_solver/recon/harness.py
from ..corpus import SampleCorpus
from ..models import Sample


def outcome_from_cookies(cookies) -> str:
    return "pass" if any(c.get("name") == "_px3" for c in cookies) else "fail"


class ReconHarness:
    """侦查骨架（Template Method）。子类实现 _open_session/_drive_to_challenge/_collect/_close_session。"""

    def __init__(self, corpus: SampleCorpus, run_id: str, meta: dict):
        self.corpus = corpus
        self.run_id = run_id
        self.meta = meta or {}

    # --- 抽象步骤 ---
    def _open_session(self):
        raise NotImplementedError

    def _drive_to_challenge(self, session):
        raise NotImplementedError

    def _collect(self, session):
        """返回 (requests, cookie_snapshots, final_cookies, pointer_stream)。"""
        raise NotImplementedError

    def _close_session(self, session):
        raise NotImplementedError

    # --- 固定流程 ---
    def run(self) -> Sample:
        session = self._open_session()
        try:
            self._drive_to_challenge(session)
            requests, snaps, final_cookies, pointer = self._collect(session)
        finally:
            self._close_session(session)
        sample = Sample(run_id=self.run_id, outcome=outcome_from_cookies(final_cookies), meta=self.meta)
        sample.requests = requests
        sample.cookie_snapshots = snaps
        sample.pointer_stream = pointer
        self.corpus.save(sample)
        return sample
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/perimeterx_solver/test_harness.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add perimeterx_solver/recon/harness.py tests/perimeterx_solver/test_harness.py
git commit -m "feat(px): ReconHarness 侦查骨架(Template Method)+落档判定"
```

---

## Task 8: 🔴⚠️ 实弹侦查入口 + 跑出协议图 + 真人黄金样本（交互，需真人长按）

**Files:**
- Create: `_recon_perimeterx.py`
- Create: `docs/superpowers/research/perimeterx-protocol-map.md`

**这是 Phase 0 的实弹任务，非单测、需真人手动长按，不能由 subagent 自动完成。** 与用户配合跑。

- [ ] **Step 1: 写实弹入口脚本**（绑定 CDP，接驳前面组件）

```python
# _recon_perimeterx.py
# -*- coding: utf-8 -*-
"""🔴 Phase 0 实弹侦查：起浏览器到 signup.live.com，录 PX 全链路 → 落语料库。
用法（机器自动跑，多半 FAIL）：python _recon_perimeterx.py bot "<proxy>"
用法（真人手动长按，求 PASS 黄金）：python _recon_perimeterx.py human "<proxy>"
"""
import asyncio, sys, time
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
import config  # noqa
from common.stealth_playwright import async_playwright
from common.browser_provider import get_browser_provider
from perimeterx_solver.corpus import SampleCorpus
from perimeterx_solver.recon.traffic_recorder import PxTrafficRecorder
from perimeterx_solver.recon.script_dumper import PxScriptDumper
from perimeterx_solver.recon.cookie_snapshotter import PxCookieSnapshotter
from perimeterx_solver.classify import is_px_url, classify_px_url, PxKind

SIGNUP = "https://signup.live.com/signup?lic=1"


async def _run(mode, proxy):
    bb = get_browser_provider()
    pid = bb.create_browser(name=f"px_recon_{mode}", proxy_str=proxy)
    info = bb.open_browser(pid)
    rec, dumper, snap = PxTrafficRecorder(), PxScriptDumper(), PxCookieSnapshotter()
    snaps, scripts = [], []
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(info.get("ws", ""))
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        pointer = []
        if mode == "human":
            # 录真人指针事件流（Phase 2 重放命脉）；init script 须在导航前注入
            await ctx.add_init_script(
                "window.__pxptr=[];['pointerdown','pointermove','pointerup'].forEach(function(t){"
                "document.addEventListener(t,function(e){window.__pxptr.push("
                "{x:e.clientX,y:e.clientY,t:e.timeStamp,type:t});},true);});")
        page = await ctx.new_page()

        async def on_response(resp):
            try:
                url = resp.url
                if not is_px_url(url):
                    return
                req = resp.request
                body = ""
                try: body = req.post_data or ""
                except Exception: pass
                rtext = ""
                try: rtext = await resp.text()
                except Exception: pass
                rec.on_request_finished(url, req.method, body, resp.status, rtext, req.headers, time.time())
                if classify_px_url(url, req.method) == PxKind.SCRIPT and rtext:
                    scripts.append(dumper.dump(url, rtext))
            except Exception:
                pass
        page.on("response", on_response)

        await page.goto(SIGNUP, wait_until="domcontentloaded", timeout=60000)
        snaps.append(snap.snapshot("on_load", time.time(), await ctx.cookies()))
        if mode == "human":
            print(">>> 真人手动：完整填表并长按过码，过了再回车 <<<")
            await asyncio.get_event_loop().run_in_executor(None, input)
            try:
                pointer = await page.evaluate("window.__pxptr || []")
            except Exception:
                pointer = []
        else:
            await asyncio.sleep(60)  # bot：等挑战出现/失败
        snaps.append(snap.snapshot("after_attempt", time.time(), await ctx.cookies()))
        final = await ctx.cookies()

    bb.close_browser(pid); bb.delete_browser(pid)
    corpus = SampleCorpus()
    from perimeterx_solver.recon.harness import outcome_from_cookies
    from perimeterx_solver.models import Sample
    s = Sample(run_id=f"{mode}_{int(time.time())}", outcome=outcome_from_cookies(final),
               meta={"mode": mode, "proxy": proxy})
    s.requests = rec.captured
    s.cookie_snapshots = snaps
    s.script_refs = scripts
    s.pointer_stream = pointer
    corpus.save(s)
    print(f"[recon] outcome={s.outcome} run_id={s.run_id} reqs={len(s.captured)} scripts={len(scripts)}")
    print(f"[recon] collector payloads={len(rec.collector_payloads())}")


if __name__ == "__main__":
    asyncio.run(_run(sys.argv[1] if len(sys.argv) > 1 else "bot",
                     sys.argv[2] if len(sys.argv) > 2 else ""))
```

- [ ] **Step 2: 冒烟（仅导入，不触网）**

Run: `python -c "import _recon_perimeterx"`
Expected: 无报错（导入成功）

- [ ] **Step 3: 🔴 跑机器 FAIL 样本（≥2 个）**

Run: `python _recon_perimeterx.py bot "<新鲜住宅代理>"`
Expected: 打印 `outcome=fail`，`reqs>0`、`scripts>0`、`collector payloads>=1`。跑 2 次得 2 个 fail 样本。

- [ ] **Step 4: 🔴⚠️ 跑真人 PASS 黄金样本（真人长按，可能多试几次）**

Run: `python _recon_perimeterx.py human "<新鲜住宅代理>"`
真人完整填表 + 手动长按过码后回车。
Expected: 打印 `outcome=pass`；`SampleCorpus().golden()` 非空。住宅 IP ~20% 成功率，过不了就再跑，直到拿到 1 个 pass。

- [ ] **Step 5: 写协议图文档**（依据语料库实测填写）

把实测结果写入 `docs/superpowers/research/perimeterx-protocol-map.md`，至少含：
- collector 端点实测 URL（确认 `PXzC5j78di.px-cdn.net/api/v2/collector` 还是 px-cloud 变体）
- 两次 collector POST 的时序与 body 字段（明文 `appId/tag/uuid/ft/pxhd` 是否如预期）
- 返回 `_px3` 的是哪一次响应、`Set-Cookie`/响应体形态
- cookie 链快照（on_load vs after_attempt 的 diff）
- collector/挑战脚本的 URL + sha256（钉死版本，供 Phase 1）

- [ ] **Step 6: 提交**

```bash
git add _recon_perimeterx.py docs/superpowers/research/perimeterx-protocol-map.md
git commit -m "feat(px): Phase0 实弹侦查入口 + 协议图(实测) + 语料库黄金样本"
```

**Gate（Phase 0 出口）**：语料库有 ≥1 真人 PASS 黄金 + ≥2 机器 FAIL；协议图文档字段齐全；脚本版本已钉死。满足才进 Phase 1。

---

# Phase 1：反混淆 & 载荷 schema

## Task 9: HookInjector (Strategy 四族 JS 片段) 🟢

**Files:**
- Create: `perimeterx_solver/analysis/__init__.py`、`perimeterx_solver/analysis/hook_injector.py`
- Test: `tests/perimeterx_solver/test_hook_injector.py`

**说明**：产出注入浏览器的 JS hook 片段。按行为锚点四族（NetworkEgress/Encoding/Behavioral/Fingerprint），都把捕获经 `window.__pxhook(kind, data)` binding 上报。关键：hook 后的原生函数 `toString` 要伪装成原生码（防反插桩）。本任务只 TDD「生成的 JS 含锚点 + 含 toString 伪装 + 可组合」。

- [ ] **Step 1: 写失败测试**

```python
# tests/perimeterx_solver/test_hook_injector.py
from perimeterx_solver.analysis.hook_injector import HookInjector, HookFamily


def test_each_family_targets_its_anchor():
    inj = HookInjector()
    assert "XMLHttpRequest.prototype.send" in inj.snippet(HookFamily.NETWORK_EGRESS)
    assert "btoa" in inj.snippet(HookFamily.ENCODING)
    assert "requestAnimationFrame" in inj.snippet(HookFamily.BEHAVIORAL)
    assert "navigator" in inj.snippet(HookFamily.FINGERPRINT)


def test_all_use_binding_and_native_tostring_guard():
    inj = HookInjector()
    js = inj.build([HookFamily.NETWORK_EGRESS, HookFamily.ENCODING])
    assert "__pxhook" in js
    assert "native code" in js  # toString 伪装存在
    # 组合应包含两族锚点
    assert "XMLHttpRequest.prototype.send" in js and "btoa" in js
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/perimeterx_solver/test_hook_injector.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

```python
# perimeterx_solver/analysis/__init__.py
```

```python
# perimeterx_solver/analysis/hook_injector.py
from enum import Enum


class HookFamily(str, Enum):
    NETWORK_EGRESS = "network_egress"
    ENCODING = "encoding"
    BEHAVIORAL = "behavioral"
    FINGERPRINT = "fingerprint"


# toString 伪装：把包装函数的 toString 改成原生码形态，防 VM 检测 hook
_TOSTRING_GUARD = """
function __pxNative(fn, name){
  try{ fn.toString = function(){ return "function " + name + "() { [native code] }"; }; }catch(e){}
  return fn;
}
"""

_SNIPPETS = {
    HookFamily.NETWORK_EGRESS: """
(function(){
  var _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = __pxNative(function(body){
    try{ window.__pxhook("egress_xhr", {url: this.__pxurl||"", body: String(body)}); }catch(e){}
    return _send.apply(this, arguments);
  }, "send");
  var _open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = __pxNative(function(m,u){ this.__pxurl=u; return _open.apply(this, arguments); }, "open");
  if (window.fetch){ var _f = window.fetch; window.fetch = __pxNative(function(u,o){
    try{ window.__pxhook("egress_fetch", {url:String(u), body:(o&&o.body)?String(o.body):""}); }catch(e){}
    return _f.apply(this, arguments); }, "fetch"); }
})();""",
    HookFamily.ENCODING: """
(function(){
  var _btoa = window.btoa;
  window.btoa = __pxNative(function(s){ try{ window.__pxhook("btoa", {len:(""+s).length, head:(""+s).slice(0,64)}); }catch(e){} return _btoa.apply(this, arguments); }, "btoa");
  var _str = JSON.stringify;
  JSON.stringify = __pxNative(function(o){ var r=_str.apply(this, arguments); try{ if(r && r.length>40) window.__pxhook("json", {head:r.slice(0,200), len:r.length}); }catch(e){} return r; }, "stringify");
})();""",
    HookFamily.BEHAVIORAL: """
(function(){
  var _raf = window.requestAnimationFrame;
  window.requestAnimationFrame = __pxNative(function(cb){ try{ window.__pxhook("raf", {t: (performance&&performance.now)?performance.now():0}); }catch(e){} return _raf.apply(this, arguments); }, "requestAnimationFrame");
  var _ael = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = __pxNative(function(type){ try{ if(type==="mousedown"||type==="pointermove"||type==="pointerdown") window.__pxhook("listener", {type:type}); }catch(e){} return _ael.apply(this, arguments); }, "addEventListener");
})();""",
    HookFamily.FINGERPRINT: """
(function(){
  try{
    var nav = navigator;
    window.__pxhook("fp_navigator", {ua: nav.userAgent, plat: nav.platform, hc: nav.hardwareConcurrency, dm: nav.deviceMemory, langs: (nav.languages||[]).join(",")});
  }catch(e){}
})();""",
}


class HookInjector:
    """生成行为锚点 hook JS（Strategy 四族）。捕获经 window.__pxhook(kind,data) 上报。"""

    def snippet(self, family: HookFamily) -> str:
        return _SNIPPETS[family]

    def build(self, families) -> str:
        parts = [_TOSTRING_GUARD] + [_SNIPPETS[f] for f in families]
        return "\n".join(parts)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/perimeterx_solver/test_hook_injector.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add perimeterx_solver/analysis/__init__.py perimeterx_solver/analysis/hook_injector.py tests/perimeterx_solver/test_hook_injector.py
git commit -m "feat(px): HookInjector 行为锚点hook(Strategy四族)+toString伪装"
```

---

## Task 10: PayloadTracer（明文→加密→出口 关联）🟢

**Files:**
- Create: `perimeterx_solver/analysis/payload_tracer.py`
- Modify: `perimeterx_solver/models.py`（追加 `TracedPayload`）
- Test: `tests/perimeterx_solver/test_payload_tracer.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/perimeterx_solver/test_payload_tracer.py
from perimeterx_solver.analysis.payload_tracer import PayloadTracer


def test_correlates_json_then_egress():
    # hook 事件流：先 json(明文) 再 egress(密文出口)
    events = [
        {"kind": "json", "data": {"head": '{"PX123":1,"mouse":[]}', "len": 50}, "t": 1.0},
        {"kind": "btoa", "data": {"head": "ZW5j", "len": 400}, "t": 1.1},
        {"kind": "egress_xhr", "data": {"url": "https://A.px-cdn.net/api/v2/collector", "body": "payload=ZW5j..."}, "t": 1.2},
    ]
    tp = PayloadTracer().trace(events)
    assert tp is not None
    assert "mouse" in tp.plaintext_head
    assert tp.egress_url.endswith("/collector")


def test_no_egress_returns_none():
    assert PayloadTracer().trace([{"kind": "json", "data": {"head": "{}", "len": 2}, "t": 1.0}]) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/perimeterx_solver/test_payload_tracer.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

先给 models.py 追加：

```python
# 追加到 perimeterx_solver/models.py 末尾
@dataclass
class TracedPayload:
    egress_url: str = ""
    egress_body_head: str = ""
    plaintext_head: str = ""
    encoding_chain: list = field(default_factory=list)  # 经过的编码事件 kind 序列
```

```python
# perimeterx_solver/analysis/payload_tracer.py
from ..classify import is_px_url
from ..models import TracedPayload

_EGRESS = ("egress_xhr", "egress_fetch")
_ENCODE = ("json", "btoa")


class PayloadTracer:
    """从 hook 事件流关联：最近一次明文(json) + 编码链 → 打到 collector 的出口。"""

    def trace(self, events):
        events = sorted(events, key=lambda e: e.get("t", 0))
        egress = next((e for e in events
                       if e["kind"] in _EGRESS and is_px_url(e["data"].get("url", ""))
                       and "/collector" in e["data"].get("url", "")), None)
        if not egress:
            return None
        t = egress["t"]
        before = [e for e in events if e.get("t", 0) <= t and e["kind"] in _ENCODE]
        json_ev = next((e for e in reversed(before) if e["kind"] == "json"), None)
        return TracedPayload(
            egress_url=egress["data"]["url"],
            egress_body_head=egress["data"].get("body", "")[:120],
            plaintext_head=(json_ev["data"]["head"] if json_ev else ""),
            encoding_chain=[e["kind"] for e in before],
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/perimeterx_solver/test_payload_tracer.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add perimeterx_solver/analysis/payload_tracer.py perimeterx_solver/models.py tests/perimeterx_solver/test_payload_tracer.py
git commit -m "feat(px): PayloadTracer 明文→编码→出口关联 + TracedPayload"
```

---

## Task 11: CryptoLocator（定位加密原语）🟢

**Files:**
- Create: `perimeterx_solver/analysis/crypto_locator.py`
- Modify: `perimeterx_solver/models.py`（追加 `CryptoFinding`）
- Test: `tests/perimeterx_solver/test_crypto_locator.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/perimeterx_solver/test_crypto_locator.py
from perimeterx_solver.analysis.crypto_locator import CryptoLocator


def test_detects_base64_when_btoa_precedes_egress():
    events = [
        {"kind": "btoa", "data": {"head": "ZW5j", "len": 400}, "t": 1.0},
        {"kind": "egress_xhr", "data": {"url": "https://A.px-cdn.net/api/v2/collector", "body": "payload=ZW5j"}, "t": 1.1},
    ]
    f = CryptoLocator().locate(events)
    assert "base64" in f.kinds


def test_detects_subtle_crypto():
    events = [{"kind": "subtle_encrypt", "data": {"algo": "AES-CBC"}, "t": 1.0},
              {"kind": "egress_xhr", "data": {"url": "https://A.px-cdn.net/api/v2/collector", "body": "x"}, "t": 1.1}]
    f = CryptoLocator().locate(events)
    assert "aes" in f.kinds
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/perimeterx_solver/test_crypto_locator.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

先给 models.py 追加：

```python
# 追加到 perimeterx_solver/models.py 末尾
@dataclass
class CryptoFinding:
    kinds: list = field(default_factory=list)   # ['base64','aes','xor',...]
    evidence: list = field(default_factory=list)  # 命中事件摘要
```

```python
# perimeterx_solver/analysis/crypto_locator.py
from ..models import CryptoFinding

_MAP = {"btoa": "base64", "subtle_encrypt": "aes", "xor": "xor"}


class CryptoLocator:
    """从 hook 事件启发式定位「最终加密串」的生成原语。"""

    def locate(self, events) -> CryptoFinding:
        kinds, ev = [], []
        for e in sorted(events, key=lambda x: x.get("t", 0)):
            k = _MAP.get(e["kind"])
            if k and k not in kinds:
                kinds.append(k)
                ev.append({"kind": e["kind"], "t": e.get("t"), "data": e.get("data")})
        return CryptoFinding(kinds=kinds, evidence=ev)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/perimeterx_solver/test_crypto_locator.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add perimeterx_solver/analysis/crypto_locator.py perimeterx_solver/models.py tests/perimeterx_solver/test_crypto_locator.py
git commit -m "feat(px): CryptoLocator 加密原语定位 + CryptoFinding"
```

---

## Task 12: PxInstrumentedSession (Facade) 工件模型 🟢

**Files:**
- Create: `perimeterx_solver/analysis/instrumented_session.py`
- Test: `tests/perimeterx_solver/test_instrumented_session.py`

**说明**：Facade，封装「在受控浏览器跑钉死 collector + 注入 hook + 收集 `__pxhook` 事件」。活体浏览器驱动是 Task 13 的薄适配；本任务 TDD「事件汇聚 + 经 Tracer/Locator 产出工件」的纯装配（用假事件列表）。

- [ ] **Step 1: 写失败测试**

```python
# tests/perimeterx_solver/test_instrumented_session.py
from perimeterx_solver.analysis.instrumented_session import InstrumentationResult


def test_result_runs_tracer_and_locator():
    events = [
        {"kind": "json", "data": {"head": '{"a":1,"mouse":[]}', "len": 30}, "t": 1.0},
        {"kind": "btoa", "data": {"head": "ZW5j", "len": 300}, "t": 1.1},
        {"kind": "egress_xhr", "data": {"url": "https://A.px-cdn.net/api/v2/collector", "body": "payload=ZW5j"}, "t": 1.2},
    ]
    r = InstrumentationResult.from_events(events)
    assert r.traced.egress_url.endswith("/collector")
    assert "base64" in r.crypto.kinds
    assert r.event_count == 3
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/perimeterx_solver/test_instrumented_session.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

```python
# perimeterx_solver/analysis/instrumented_session.py
from dataclasses import dataclass

from .payload_tracer import PayloadTracer
from .crypto_locator import CryptoLocator


@dataclass
class InstrumentationResult:
    events: list
    traced: object
    crypto: object

    @property
    def event_count(self):
        return len(self.events)

    @classmethod
    def from_events(cls, events):
        return cls(events=events,
                   traced=PayloadTracer().trace(events),
                   crypto=CryptoLocator().locate(events))


class PxInstrumentedSession:
    """Facade：跑钉死 collector + 注入 hook + 汇聚 __pxhook 事件 → InstrumentationResult。

    活体驱动（连 CDP、addInitScript 注入 hook、exposeBinding 收事件）在 _instrument_perimeterx.py。
    这里只暴露 analyze() 纯装配，便于单测与复用。
    """

    def analyze(self, events) -> InstrumentationResult:
        return InstrumentationResult.from_events(events)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/perimeterx_solver/test_instrumented_session.py -q`
Expected: PASS（1 passed）

- [ ] **Step 5: 提交**

```bash
git add perimeterx_solver/analysis/instrumented_session.py tests/perimeterx_solver/test_instrumented_session.py
git commit -m "feat(px): PxInstrumentedSession(Facade)+InstrumentationResult 工件装配"
```

---

## Task 13: 🔴 实弹插桩入口 + 跑出明文 schema + 定位 crypto（交互/反混淆）

**Files:**
- Create: `_instrument_perimeterx.py`
- Create: `docs/superpowers/research/perimeterx-payload-schema.md`
- Create: `docs/superpowers/research/perimeterx-crypto-spec.md`

**实弹反混淆，非单测。与用户配合跑；可能需多轮 hook 迭代。**

- [ ] **Step 1: 写实弹插桩入口**（连 CDP、`add_init_script` 注入 hook、`expose_binding` 收 `__pxhook` 事件，跑到挑战，导出事件 + 工件）

```python
# _instrument_perimeterx.py
# -*- coding: utf-8 -*-
"""🔴 Phase 1 实弹插桩：在受控浏览器跑 PX collector，注入行为锚点 hook，捕获明文载荷 + 定位 crypto。
用法：python _instrument_perimeterx.py "<proxy>"
"""
import asyncio, json, sys, time
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
import config  # noqa
from common.stealth_playwright import async_playwright
from common.browser_provider import get_browser_provider
from perimeterx_solver.analysis.hook_injector import HookInjector, HookFamily
from perimeterx_solver.analysis.instrumented_session import PxInstrumentedSession

SIGNUP = "https://signup.live.com/signup?lic=1"


async def _run(proxy):
    events = []
    inj = HookInjector()
    hook_js = inj.build([HookFamily.NETWORK_EGRESS, HookFamily.ENCODING,
                         HookFamily.BEHAVIORAL, HookFamily.FINGERPRINT])
    bb = get_browser_provider()
    pid = bb.create_browser(name="px_instr", proxy_str=proxy)
    info = bb.open_browser(pid)
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(info.get("ws", ""))
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        await ctx.expose_binding("__pxhook", lambda src, kind, data: events.append(
            {"kind": kind, "data": data, "t": time.time()}))
        await ctx.add_init_script(hook_js)
        page = await ctx.new_page()
        await page.goto(SIGNUP, wait_until="domcontentloaded", timeout=60000)
        print(">>> 让挑战出现（真人或自动皆可）；收集足够事件后回车 <<<")
        await asyncio.get_event_loop().run_in_executor(None, input)
    bb.close_browser(pid); bb.delete_browser(pid)

    with open("_px_events.json", "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)
    result = PxInstrumentedSession().analyze(events)
    print(f"[instr] events={result.event_count}")
    print(f"[instr] traced egress={getattr(result.traced,'egress_url',None)}")
    print(f"[instr] plaintext head={getattr(result.traced,'plaintext_head','')[:200]}")
    print(f"[instr] crypto kinds={result.crypto.kinds}")


if __name__ == "__main__":
    asyncio.run(_run(sys.argv[1] if len(sys.argv) > 1 else ""))
```

- [ ] **Step 2: 冒烟（仅导入）**

Run: `python -c "import _instrument_perimeterx"`
Expected: 无报错

- [ ] **Step 3: 🔴 跑实弹插桩，导出明文载荷**

Run: `python _instrument_perimeterx.py "<住宅代理>"`
让挑战出现、长按。Expected: 打印捕获到的 `plaintext head`（明文传感器对象片段）+ `crypto kinds`（如 base64/aes）；`_px_events.json` 落盘。
若 `__pxhook` 没收到事件 → VM 可能反插桩，回 Task 9 调 hook（换注入时机/锚点/toString 伪装），迭代。

- [ ] **Step 4: 写载荷 schema 文档**

把明文载荷字段写入 `docs/superpowers/research/perimeterx-payload-schema.md`：字段全清单、类型、标注哪些是行为字段（鼠标轨迹/mousedown 频率/坐标方差/rAF/时序）、哪些是静态指纹。

- [ ] **Step 5: 写 crypto 规格文档**

把定位到的加密/签名写入 `docs/superpowers/research/perimeterx-crypto-spec.md`：算法（base64/XOR/AES…）、密钥来源/派生、IV/nonce、明文→密文的完整链路。这是 Task 14 解密器的依据。

- [ ] **Step 6: 提交**

```bash
git add _instrument_perimeterx.py docs/superpowers/research/perimeterx-payload-schema.md docs/superpowers/research/perimeterx-crypto-spec.md
git commit -m "feat(px): Phase1 实弹插桩 + 明文schema + crypto规格(实测)"
```

**Gate（crypto 可还原？）**：crypto 规格能支撑 Task 14 重实现解密。若密钥 VM 现算不可静态复刻 → 在 crypto-spec 标注，转「VM-oracle 兜底」（隔离 JS 运行时当解/签机），此分支并入 Phase 2 评估。

---

## Task 14: PayloadDecryptor (Strategy)（依 Task 13 实测算法实现）🟢

**Files:**
- Create: `perimeterx_solver/analysis/decryptor.py`
- Test: `tests/perimeterx_solver/test_decryptor.py`

**说明**：算法来自 Task 13 的 crypto-spec。下面以「实测确认为 Base64+XOR」为示范骨架（实际按 spec 调整 `_XorBase64Decryptor` 的密钥/步骤）。接口稳定，算法可换实现（Strategy）。**先用 Task 13 导出的真实 `_px_events.json`/语料库黄金样本的密文做断言**。

- [ ] **Step 1: 写失败测试**（用一个已知 明文/密钥/密文 的小三元组锁住算法正确性；实测后用黄金样本真实密文替换）

```python
# tests/perimeterx_solver/test_decryptor.py
import base64
from perimeterx_solver.analysis.decryptor import XorBase64Decryptor, PayloadDecryptor


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def test_xor_base64_decrypts_known_triple():
    key = b"PXkey"
    plaintext = b'{"appId":"PXzC5j78di","mouse":[[1,2,3]]}'
    blob = base64.b64encode(_xor(plaintext, key)).decode()
    dec = XorBase64Decryptor(key=key)
    out = dec.decrypt(blob, context={})
    assert out["appId"] == "PXzC5j78di"
    assert out["mouse"] == [[1, 2, 3]]


def test_decryptor_is_strategy_interface():
    assert issubclass(XorBase64Decryptor, PayloadDecryptor)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/perimeterx_solver/test_decryptor.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**（Strategy 接口 + 按实测算法的具体实现）

```python
# perimeterx_solver/analysis/decryptor.py
import base64
import json


class PayloadDecryptor:
    """密文 → 明文 dict 的策略接口（Strategy）。算法随 PX 版本可换实现。"""

    def decrypt(self, encrypted_blob: str, context: dict) -> dict:
        raise NotImplementedError


class XorBase64Decryptor(PayloadDecryptor):
    """示范实现：Base64 解码 → XOR 解密 → JSON。密钥/步骤按 crypto-spec 实测调整。"""

    def __init__(self, key: bytes):
        self.key = key

    def _xor(self, data: bytes) -> bytes:
        k = self.key
        return bytes(b ^ k[i % len(k)] for i, b in enumerate(data))

    def decrypt(self, encrypted_blob: str, context: dict) -> dict:
        raw = base64.b64decode(encrypted_blob)
        plain = self._xor(raw)
        return json.loads(plain.decode("utf-8", "replace"))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/perimeterx_solver/test_decryptor.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 🔴 用黄金样本真实密文验证**

写一次性校验：`python -c "from perimeterx_solver.corpus import SampleCorpus; ..."` 取语料库 golden 样本里 collector 密文，用 `XorBase64Decryptor`（实测密钥）解密，确认得到可读 JSON。把结果记入 crypto-spec。**若解不出 → 算法/密钥不对，回 Task 13 继续逆。**

- [ ] **Step 6: 提交**

```bash
git add perimeterx_solver/analysis/decryptor.py tests/perimeterx_solver/test_decryptor.py
git commit -m "feat(px): PayloadDecryptor(Strategy)+实测算法 解密载荷"
```

---

## Task 15: SchemaDiffer（真人 vs 机器 明文 diff）🟢

**Files:**
- Create: `perimeterx_solver/analysis/schema_differ.py`
- Test: `tests/perimeterx_solver/test_schema_differ.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/perimeterx_solver/test_schema_differ.py
from perimeterx_solver.analysis.schema_differ import SchemaDiffer


def test_diff_ranks_differing_fields():
    human = {"appId": "A", "mousedownFreq": 7, "coordVar": 12.3, "raf": 60}
    bot = {"appId": "A", "mousedownFreq": 0, "coordVar": 0.0, "raf": 60}
    d = SchemaDiffer().diff(human, bot)
    names = [x["field"] for x in d]
    assert "mousedownFreq" in names and "coordVar" in names
    assert "appId" not in names and "raf" not in names


def test_diff_reports_missing_fields():
    d = SchemaDiffer().diff({"a": 1, "b": 2}, {"a": 1})
    assert any(x["field"] == "b" and x["bot"] is None for x in d)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/perimeterx_solver/test_schema_differ.py -q`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 写实现**

```python
# perimeterx_solver/analysis/schema_differ.py
class SchemaDiffer:
    """diff 真人 PASS vs 机器 FAIL 明文载荷，列出判别字段（Phase 2 靶向清单）。"""

    def diff(self, human: dict, bot: dict):
        out = []
        for k in sorted(set(human) | set(bot)):
            hv, bv = human.get(k), bot.get(k)
            if hv != bv:
                out.append({"field": k, "human": hv, "bot": bv})
        return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/perimeterx_solver/test_schema_differ.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 🔴 跑真实差分 + 写差分报告**

用 Task 14 的解密器把语料库里真人 PASS 与机器 FAIL 的 collector 密文都解成明文，喂 `SchemaDiffer`，把判别字段写入 `docs/superpowers/research/perimeterx-diff-report.md`——这是 Phase 2 要精准伪造的清单。

- [ ] **Step 6: 提交**

```bash
git add perimeterx_solver/analysis/schema_differ.py tests/perimeterx_solver/test_schema_differ.py docs/superpowers/research/perimeterx-diff-report.md
git commit -m "feat(px): SchemaDiffer 真人vs机器判别字段 + 差分报告"
```

**Gate（Phase 1 出口）**：明文 schema 文档齐全；crypto-spec 可支撑重实现；解密器能解黄金样本；差分报告给出非空判别字段清单。满足即 Phase 0–1 地基完成。

---

## 收尾：全量回归

- [ ] 跑 `python -m pytest tests/perimeterx_solver -q`，全绿。
- [ ] 跑 `python -m pytest -q`，确认全量失败数仍为基线 19（无新增回归）。
- [ ] 更新记忆 [[outlook-perimeterx-solvers]]：地基完成、协议图/schema/crypto/diff 四文档落地、Phase 2 待启。

---

# Phase 2 / Phase 3 里程碑（门后目标，不在本计划拆解）

## Phase 2 里程碑：伪造 & 校验（核心难关）
依 Phase 1 的 schema + crypto-spec + 差分报告：
- `PayloadBuilder`(Builder) 重实现明文载荷装配（Python）。
- `BehavioralSource`(Strategy)：合成「类真人」行为（按差分报告里 mousedown 频率/坐标方差/rAF 分布生成）或重放 Phase 0 真人指针特征。
- `Signer`(Strategy)：静态重实现 或 VM-oracle 兜底。
- 差分校验台：POST collector 端点 → 判「接受」+ 取 `_px3` → 对照黄金样本迭代收敛。
- **Gate**：稳定拿到 `_px3` 通过 cookie，接受率达标。

## Phase 3 里程碑：产品化 & 接入
- 包成本地 HTTP 服务 `PxSolverService`(Facade)，对齐 `_funcaptcha_solver` 的 createTask/getTask。
- `register_outlook_standalone` 长按段替换为「调 PX 服务拿 cookie 注入同会话」，Arkose HSol 仍走现有 solver。
- 失败安全：solver 不可用→回退浏览器长按（FallbackPolicy 语义）。
- **Gate**：E2E 全 HTTP 出号。
