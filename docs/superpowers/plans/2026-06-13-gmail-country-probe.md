# Gmail 国家可用性自动探测 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 注册 google 时按价格从低到高自动逐国试号，真收到验证码的国家记入「可用库」并建号，失败国家进 24h 冷却，断点续探，全程不超价格上限。

**Architecture:** 核心策略抽成 `common/country_probe.py` 纯函数+HTTP helper（可单测）；`browser_phone_and_finalize` 在 `auto_probe` 开时编排它逐国试；可用库存 config_service `gmail_country_probe`；前端加开关+可用库展示。

**Tech Stack:** Python 3.13 · requests(同步,与现有 `_svc_acquire` 一致) · pytest(root `tests/`) · React/antd/vitest

**约定：** 后端纯/HTTP 函数测试在 repo 根跑 `cd f:/reg-factory && python -m pytest tests/test_country_probe.py -v`（`tests/conftest.py` 已把根加入 sys.path，`from common.country_probe import ...` 可用）。前端在 `f:/reg-factory/frontend`。参考 spec `docs/superpowers/specs/2026-06-13-gmail-country-probe-design.md`。

**已确认的契约（直接用）：**
- `GET /sms/providers/{provider}/prices?service=go` → `data=[{country,country_name,cost,count}]`（cost=该国最低价）
- config_service：`GET /config/gmail_country_probe`→`data.value`(dict)；`PUT /config/{key}` body **必须含 key**：`{key,value}`
- gateway(8000) 转发 `/config/*` 和 `/sms/*`；注册子进程同步 requests 调 localhost 须带 `proxies={"http":None,"https":None}`
- `browser_phone_and_finalize(page, profile, ctx, profile_id, sms_config)`：`sms_config` 含 `provider/country/max_price/fixed_price`，本计划加 `auto_probe`
- 现有取号 `_svc_acquire(provider, country, max_price, fixed, service="go")` 已透传 maxPrice

---

## File Structure

- `common/country_probe.py` — **新建**。纯函数 `build_probe_sequence`/`mark_available`/`mark_failed` + HTTP helper `probe_load`/`probe_save`/`probe_prices`。一个文件，职责=「国家探测的状态与策略」。
- `tests/test_country_probe.py` — **新建**。上述全部的单测。
- `register_gmail_hybrid.py` — **改**。`browser_phone_and_finalize` 加 `auto_probe` 分支（编排 country_probe 逐国试）。
- `frontend/src/pages/SmsConfigPage.tsx` — **改**。`auto_probe` 开关 + 可用国家库展示/删除。
- `frontend/src/pages/SmsConfigPage.gmail.test.tsx` — **改**。新增断言。

---

## Task 1: `build_probe_sequence` 候选国家序列（纯函数）

**Files:** Create `common/country_probe.py`、`tests/test_country_probe.py`

- [ ] **Step 1: 失败测试** `tests/test_country_probe.py`：
```python
from common.country_probe import build_probe_sequence


def test_sequence_available_first_then_new_by_price():
    prices = [
        {"country": "4", "country_name": "菲律宾", "cost": 0.025, "count": 100},
        {"country": "52", "country_name": "泰国", "cost": 0.1, "count": 100},
        {"country": "8", "country_name": "肯尼亚", "cost": 0.02, "count": 100},
        {"country": "99", "country_name": "贵国", "cost": 0.5, "count": 100},  # 超 max_price
    ]
    probe = {"available": [{"country": "52", "name": "泰国", "price": 0.1, "last_ok": 1000}], "failed": {}}
    seq = build_probe_sequence(prices, probe, max_price=0.2, now=2000)
    # available(泰国)优先 → 未试国家按价升序(肯尼亚0.02、菲律宾0.025)；超价的99跳过
    assert [s["country"] for s in seq] == ["52", "8", "4"]
    assert seq[0]["name"] == "泰国" and seq[1]["name"] == "肯尼亚"


def test_sequence_skips_failed_in_cooldown():
    prices = [{"country": "7", "country_name": "马来", "cost": 0.1, "count": 100}]
    probe = {"available": [], "failed": {"7": {"reason": "x", "last_fail": 2000}}}
    assert build_probe_sequence(prices, probe, max_price=0.2, now=3000, cooldown_seconds=86400) == []
    # 冷却过 → 马来重新进候选
    seq = build_probe_sequence(prices, probe, max_price=0.2, now=2000 + 90000, cooldown_seconds=86400)
    assert [s["country"] for s in seq] == ["7"]
```

- [ ] **Step 2: 跑红** `cd f:/reg-factory && python -m pytest tests/test_country_probe.py -v` → FAIL（模块不存在）

- [ ] **Step 3: 实现** `common/country_probe.py`：
```python
"""Gmail 注册国家可用性探测：候选序列策略 + 可用库读写。
纯函数易测；HTTP helper 经 gateway 读写 config_service。"""


def build_probe_sequence(prices, probe, max_price, now, cooldown_seconds=86400):
    """构建候选国家序列：available(可用库,按价升序) 优先 + 未试国家(按价升序)，
    全部 cost ≤ max_price 且跳过 failed 冷却内的国家。
    prices: [{country, country_name, cost, count}]；probe: {available:[...], failed:{...}}
    返回 [{country, name, price}]。"""
    mp = float(max_price)
    failed = probe.get("failed", {}) or {}

    def in_cooldown(c):
        f = failed.get(str(c))
        return bool(f) and (now - f.get("last_fail", 0) < cooldown_seconds)

    avail_seq, avail_ids = [], set()
    for a in probe.get("available", []) or []:
        c = str(a["country"])
        avail_ids.add(c)
        if float(a.get("price", 0)) <= mp and not in_cooldown(c):
            avail_seq.append({"country": c, "name": a.get("name", ""), "price": float(a.get("price", 0))})
    avail_seq.sort(key=lambda x: x["price"])

    new_seq = []
    for p in prices:
        c = str(p["country"])
        if c in avail_ids or in_cooldown(c) or float(p.get("cost", 0)) > mp:
            continue
        new_seq.append({"country": c, "name": p.get("country_name", ""), "price": float(p.get("cost", 0))})
    new_seq.sort(key=lambda x: x["price"])
    return avail_seq + new_seq
```

- [ ] **Step 4: 跑绿** `cd f:/reg-factory && python -m pytest tests/test_country_probe.py -v` → PASS

- [ ] **Step 5: Commit**
```bash
cd f:/reg-factory && git add common/country_probe.py tests/test_country_probe.py && git commit -m "feat(probe): build_probe_sequence 候选国家序列(available优先+未试按价升序+冷却/超价跳过)"
```

---

## Task 2: `mark_available` / `mark_failed`（可用库更新，纯函数）

**Files:** Modify `common/country_probe.py`、`tests/test_country_probe.py`

- [ ] **Step 1: 失败测试**（追加到 `tests/test_country_probe.py`）：
```python
from common.country_probe import mark_available, mark_failed


def test_mark_available_adds_and_clears_failed():
    probe = {"available": [], "failed": {"52": {"reason": "x", "last_fail": 1}}}
    mark_available(probe, "52", "泰国", 0.1, 2000)
    assert probe["available"] == [{"country": "52", "name": "泰国", "price": 0.1, "last_ok": 2000}]
    assert "52" not in probe["failed"]


def test_mark_available_replaces_existing():
    probe = {"available": [{"country": "52", "name": "泰国", "price": 0.1, "last_ok": 1}], "failed": {}}
    mark_available(probe, "52", "泰国", 0.12, 3000)
    assert len(probe["available"]) == 1 and probe["available"][0]["last_ok"] == 3000


def test_mark_failed_demotes_available():
    probe = {"available": [{"country": "52", "name": "泰国", "price": 0.1, "last_ok": 1}], "failed": {}}
    mark_failed(probe, "52", "用过太多次", 2000)
    assert probe["available"] == []
    assert probe["failed"]["52"] == {"reason": "用过太多次", "last_fail": 2000}
```

- [ ] **Step 2: 跑红** `cd f:/reg-factory && python -m pytest tests/test_country_probe.py -k mark -v` → FAIL（未定义）

- [ ] **Step 3: 实现**（追加到 `common/country_probe.py`）：
```python
def mark_available(probe, country, name, price, now):
    """记/更新可用国家；从 failed 移除。原地改 probe。"""
    c = str(country)
    probe.setdefault("available", [])
    probe.setdefault("failed", {})
    probe["available"] = [a for a in probe["available"] if str(a["country"]) != c]
    probe["available"].append({"country": c, "name": name, "price": float(price), "last_ok": now})
    probe["failed"].pop(c, None)


def mark_failed(probe, country, reason, now):
    """记失败国家(进冷却)；若在 available 则移除(降级)。原地改 probe。"""
    c = str(country)
    probe.setdefault("available", [])
    probe.setdefault("failed", {})
    probe["available"] = [a for a in probe["available"] if str(a["country"]) != c]
    probe["failed"][c] = {"reason": reason, "last_fail": now}
```

- [ ] **Step 4: 跑绿** `cd f:/reg-factory && python -m pytest tests/test_country_probe.py -v` → 全 PASS

- [ ] **Step 5: Commit**
```bash
cd f:/reg-factory && git add common/country_probe.py tests/test_country_probe.py && git commit -m "feat(probe): mark_available/mark_failed 可用库更新(成功记录+失败降级)"
```

---

## Task 3: `probe_load` / `probe_save` / `probe_prices`（HTTP helper）

**Files:** Modify `common/country_probe.py`、`tests/test_country_probe.py`

- [ ] **Step 1: 失败测试**（追加）：
```python
import common.country_probe as cp


def test_probe_load_parses_value(monkeypatch):
    class _R:
        def json(self):
            return {"data": {"value": {"available": [{"country": "52"}], "failed": {}}}}
    monkeypatch.setattr(cp.requests, "get", lambda *a, **k: _R())
    probe = cp.probe_load()
    assert probe["available"][0]["country"] == "52" and probe["failed"] == {}


def test_probe_load_defaults_on_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("conn")
    monkeypatch.setattr(cp.requests, "get", boom)
    assert cp.probe_load() == {"available": [], "failed": {}}


def test_probe_save_puts_key_and_value(monkeypatch):
    captured = {}
    def fake_put(url, json=None, **k):
        captured["url"] = url
        captured["json"] = json
        class _R:
            pass
        return _R()
    monkeypatch.setattr(cp.requests, "put", fake_put)
    cp.probe_save({"available": [], "failed": {}})
    assert captured["url"].endswith("/config/gmail_country_probe")
    assert captured["json"]["key"] == "gmail_country_probe"
    assert captured["json"]["value"] == {"available": [], "failed": {}}


def test_probe_prices_returns_data(monkeypatch):
    class _R:
        def json(self):
            return {"data": [{"country": "52", "country_name": "泰国", "cost": 0.1, "count": 9}]}
    monkeypatch.setattr(cp.requests, "get", lambda *a, **k: _R())
    rows = cp.probe_prices("hero_sms")
    assert rows[0]["country"] == "52"
```

- [ ] **Step 2: 跑红** `cd f:/reg-factory && python -m pytest tests/test_country_probe.py -k probe_ -v` → FAIL

- [ ] **Step 3: 实现**（`common/country_probe.py` 顶部加 `import requests`，并追加）：
```python
import requests

_GW = "http://localhost:8000"
_NOPROXY = {"http": None, "https": None}


def probe_load(base_url=_GW):
    """GET 可用库；异常/缺失 → 空库。"""
    try:
        r = requests.get(f"{base_url}/config/gmail_country_probe", timeout=10, proxies=_NOPROXY)
        v = (r.json().get("data") or {}).get("value")
        if isinstance(v, dict):
            v.setdefault("available", [])
            v.setdefault("failed", {})
            return v
    except Exception:
        pass
    return {"available": [], "failed": {}}


def probe_save(probe, base_url=_GW):
    """PUT 回写可用库（body 必须含 key）。"""
    try:
        requests.put(f"{base_url}/config/gmail_country_probe",
                     json={"key": "gmail_country_probe", "value": probe},
                     timeout=10, proxies=_NOPROXY)
    except Exception:
        pass


def probe_prices(provider, base_url=_GW):
    """GET 该 provider 的全量国家+价格（go 服务）。"""
    try:
        r = requests.get(f"{base_url}/sms/providers/{provider}/prices",
                         params={"service": "go"}, timeout=20, proxies=_NOPROXY)
        return r.json().get("data") or []
    except Exception:
        return []
```
（`import requests` 放文件顶部；上面三函数追加到末尾。）

- [ ] **Step 4: 跑绿** `cd f:/reg-factory && python -m pytest tests/test_country_probe.py -v` → 全 PASS

- [ ] **Step 5: Commit**
```bash
cd f:/reg-factory && git add common/country_probe.py tests/test_country_probe.py && git commit -m "feat(probe): probe_load/save/prices HTTP helper(经 gateway 读写可用库)"
```

---

## Task 4: `browser_phone_and_finalize` 接入 auto_probe 逐国探测

**Files:** Modify `register_gmail_hybrid.py`（无单测，靠 py_compile + Task 6 实跑）

> 改造前先读当前 `browser_phone_and_finalize`（约 line 296-410）确认精确文本。核心改三处：解析区、取号循环每轮选国家、成功/失败回写。

- [ ] **Step 1: 解析区加 auto_probe + 加载候选序列**
在 `sms_config` 解析段（`svc_fixed = ...` 之后、`def _release` 之前）插入：
```python
    auto_probe = bool(sms_config.get("auto_probe")) and use_svc
    probe = None
    seq = []
    if auto_probe:
        import time as _time
        from common.country_probe import (
            build_probe_sequence, mark_available, mark_failed, probe_load, probe_save, probe_prices,
        )
        probe = probe_load()
        _prices = probe_prices(svc_provider)
        seq = build_probe_sequence(_prices, probe, svc_maxprice, int(_time.time()))
        log(f"[probe] 候选国家 {len(seq)} 个(≤{svc_maxprice}): {[s['country'] for s in seq[:8]]}")
        if not seq:
            log("[probe] 无候选国家(都在冷却或超价)，放弃", "WARN")
            return None
```

- [ ] **Step 2: 取号循环每轮选国家**
把循环体开头取号前，确定本轮国家。当前循环是 `for attempt in range(1, max_tries + 1):` → `if use_svc:` 分支用固定 `svc_country`。改为：在 `for attempt` 之后、`try:` 内取号前加：
```python
        if auto_probe:
            if attempt - 1 >= len(seq):
                log("[probe] 候选国家已试完", "WARN")
                break
            _cur = seq[attempt - 1]
            cur_country, cur_name, cur_price = _cur["country"], _cur["name"], _cur["price"]
        else:
            cur_country = svc_country
```
并把 use_svc 取号那行的国家参数从 `svc_country` 改为 `cur_country`：
```python
                _ph, _oid = _svc_acquire(svc_provider, cur_country, svc_maxprice, svc_fixed, service=hero_svc)
```
取号成功日志也带国家名：
```python
                log(f"[sms] 号(svc): {e164}" + (f" [{cur_name} {cur_country} ${cur_price}]" if auto_probe else ""))
```

- [ ] **Step 3: 成功收码处 mark_available，失败处 mark_failed**
- 收到码、`phone_used = e164` 那段（建号前）加：
```python
            if auto_probe and probe is not None:
                mark_available(probe, cur_country, cur_name, cur_price, int(__import__("time").time()))
```
- 「没收到码换号」分支（`_release(pkey)` 后）加：
```python
            if auto_probe and probe is not None:
                mark_failed(probe, cur_country, "无码", int(__import__("time").time()))
```
- 「号不可用/被拒」分支（`consecutive_reject += 1` 那段，`_release(pkey)` 后）加：
```python
            if auto_probe and probe is not None:
                mark_failed(probe, cur_country, diag[:40], int(__import__("time").time()))
```
- 取号失败 `except Exception as e:`（`log("[sms] 取号失败...")` 那段）加（auto_probe 时该国记失败）：
```python
            if auto_probe and probe is not None and 'cur_country' in dir():
                mark_failed(probe, cur_country, f"取号失败:{str(e)[:30]}", int(__import__("time").time()))
```

- [ ] **Step 4: 回写可用库**
在函数 `return` 结果前（手机验证成功收尾后，以及 `if not phone_used: return None` 前）统一回写。最稳妥：在取号大循环 `for` 结束之后、`if not phone_used:` 判断之前插入：
```python
    if auto_probe and probe is not None:
        probe_save(probe)
        log(f"[probe] 回写可用库: 可用{len(probe.get('available', []))}国 / 冷却{len(probe.get('failed', {}))}国")
```
（注意：`break` 退出循环后也会执行到这里，成功/失败都回写。）

- [ ] **Step 5: 编译校验**
Run: `cd f:/reg-factory && python -m py_compile register_gmail_hybrid.py`
Expected: 无输出（编译通过）

- [ ] **Step 6: Commit**
```bash
cd f:/reg-factory && git add register_gmail_hybrid.py && git commit -m "feat(gmail-reg): auto_probe 逐国探测(候选序列+收码记可用+失败冷却+回写可用库)"
```

---

## Task 5: 前端 auto_probe 开关 + 可用国家库展示

**Files:** Modify `frontend/src/pages/SmsConfigPage.tsx`、`frontend/src/pages/SmsConfigPage.gmail.test.tsx`

> 现有 `gmailCfg` 是 `{provider,country,max_price,fixed_price}`，`saveGmailCfg` PUT `gmail_sms_config`。本任务加 `auto_probe` 字段 + 可用库读取/展示/删除。

- [ ] **Step 1: 失败测试**（追加到 `SmsConfigPage.gmail.test.tsx`）。先在 `beforeEach` 的 fetch mock 里加 `gmail_country_probe` 分支（放 `/config/gmail_sms_config` 分支前，因两者都含 `/config/`，更具体的在前）：
```tsx
    if (url.includes('/config/gmail_country_probe')) return Promise.resolve({ json: () => Promise.resolve({ data: { value: { available: [{ country: '52', name: '泰国', price: 0.1, last_ok: 1718000000 }], failed: {} } } }) })
```
再加测试：
```tsx
  it('展示可用国家库', async () => {
    renderWithProviders(<SmsConfigPage />)
    await waitFor(() => expect(screen.getByText(/可用国家库/)).toBeInTheDocument())
    expect(screen.getByText(/泰国/)).toBeInTheDocument()
  })
```

- [ ] **Step 2: 跑红** `cd f:/reg-factory/frontend && npx vitest run src/pages/SmsConfigPage.gmail.test.tsx` → FAIL（无「可用国家库」）

- [ ] **Step 3: 实现** `SmsConfigPage.tsx`：
(a) `gmailCfg` 类型与初值加 `auto_probe`：
```tsx
  const [gmailCfg, setGmailCfg] = useState<{provider:string;country:string;max_price:string;fixed_price:boolean;auto_probe:boolean}>({ provider: 'hero_sms', country: '', max_price: '0.2', fixed_price: false, auto_probe: false })
```
(b) 加可用库 state + 加载：
```tsx
  const [gmailAvail, setGmailAvail] = useState<{country:string;name:string;price:number;last_ok:number}[]>([])

  useEffect(() => {
    fetch('/api/config/gmail_country_probe').then(r => r.json())
      .then(res => setGmailAvail(res.data?.value?.available || [])).catch(() => {})
  }, [])
```
(c) 删除某可用国家（写回 gmail_country_probe）：
```tsx
  const removeAvail = (country: string) => {
    const next = gmailAvail.filter(a => a.country !== country)
    setGmailAvail(next)
    fetch('/api/config/gmail_country_probe').then(r => r.json()).then(res => {
      const probe = res.data?.value || { available: [], failed: {} }
      probe.available = next
      fetch('/api/config/gmail_country_probe', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'gmail_country_probe', value: probe }),
      })
    }).catch(() => {})
  }
```
(d) JSX：在「固定价格」Switch 后、保存按钮前加自动探测开关：
```tsx
          <Form.Item label="自动探测国家"><Switch checked={gmailCfg.auto_probe} onChange={(v) => setGmailCfg({ ...gmailCfg, auto_probe: v })} /></Form.Item>
```
(e) JSX：在价位档区块后（`</Card>` 前）加可用国家库表格：
```tsx
        <div style={{ marginTop: 16 }}>
          <div style={{ marginBottom: 8, color: '#888', fontSize: 13 }}>可用国家库（注册时按价优先复用，验证失败会自动移入冷却；可手动删除变烂的）</div>
          <Table rowKey="country" size="small" pagination={false}
            dataSource={gmailAvail}
            columns={[
              { title: '国家', dataIndex: 'name', key: 'name', render: (n: string, r: any) => n || r.country },
              { title: '价格', dataIndex: 'price', key: 'price' },
              { title: '上次验证', dataIndex: 'last_ok', key: 'last_ok', render: (t: number) => t ? new Date(t * 1000).toLocaleString() : '-' },
              { title: '操作', key: 'op', render: (_: any, r: any) => <Button type="link" danger size="small" onClick={() => removeAvail(r.country)}>删除</Button> },
            ]} />
        </div>
```

- [ ] **Step 4: 跑绿 + 回归 + 类型**
```
cd f:/reg-factory/frontend
npx vitest run src/pages/SmsConfigPage.gmail.test.tsx src/pages/SmsConfigPage.test.tsx
npx tsc --noEmit
```
预期：全 PASS（新「展示可用国家库」+ 现有都绿）；tsc 无报错。`auto_probe` 随 `saveGmailCfg` 的 `JSON.stringify({ key:'gmail_sms_config', value: gmailCfg })` 自动带上（gmailCfg 已含 auto_probe），无需改 saveGmailCfg。

- [ ] **Step 5: Commit**
```bash
cd f:/reg-factory && git add frontend/src/pages/SmsConfigPage.tsx frontend/src/pages/SmsConfigPage.gmail.test.tsx && git commit -m "feat(frontend): 自动探测国家开关 + 可用国家库展示/删除"
```

---

## Task 6: 重启服务 + 端到端实测（用户配合）

- [ ] **Step 1: 全量后端回归**
Run: `cd f:/reg-factory && python -m pytest tests/test_country_probe.py -q` 和 `cd f:/reg-factory/services && python -m pytest tests/sms_service/ tests/gateway/ -q`
Expected: 全 PASS

- [ ] **Step 2: 重启 sms_service 不需要**（本功能未改 sms_service 路由）；gateway 不需要（未改）；config_service 不需要。注册子进程是 spawn fresh import，`register_gmail_hybrid.py` + `common/country_probe.py` 改动**下次注册自动生效**。**前端 vite 需重启**（Windows 下 Edit 改 .tsx vite 常不热更——见记忆 [[vite-windows-no-hmr-on-edit]]）：杀 3000 → 删 `frontend/node_modules/.vite` → `cd frontend && npx vite` → warm `http://localhost:3000/`。

- [ ] **Step 3: 前端验证** SmsConfigPage：开「自动探测国家」开关 → 保存；页面应展示「可用国家库」表格（初次为空）。

- [ ] **Step 4: 注册实测** Google 注册 count=1，盯日志：
  - `[probe] 候选国家 N 个(≤0.2): [...]` — 候选序列构建
  - `[sms] 号(svc): +xx... [国家名 ID $价]` — 逐国试号
  - 某国收到码建号 → `[probe] 回写可用库: 可用1国 / 冷却K国`
  - 再次注册：候选序列里泰国(或上次成功国)排最前（available 优先）

- [ ] **Step 5: 验证可用库持久化**
Run: `Invoke-RestMethod "http://localhost:8000/config/gmail_country_probe"`（PowerShell）
Expected: `data.value.available` 含建号成功的国家，`failed` 含被拒国家

---

## Self-Review

**1. Spec coverage：** §1 数据结构→T1-T3(probe dict 读写/更新)；§2 候选策略→T1；§3 取号循环改造+双重价格保证→T4(候选只含≤max_price + _svc_acquire 传 maxPrice)；§4 probe 读写→T3；§5 auto_probe 开关→T4(读)+T5(写);§6 前端→T5；§7 链路→T4+T5;§8 冷却24h/降级→T1(cooldown)/T2(mark_failed 降级)；§9 测试→T1-T3 单测+T5 前端+T4/T6 实跑。✅
**2. Placeholder：** 每 step 含完整代码/命令。T4 是 root 脚本改造（无单测），给了精确插入点+代码片段+py_compile+实跑，已说明。✅
**3. 类型一致：** `build_probe_sequence(prices, probe, max_price, now, cooldown_seconds)`、`mark_available(probe,country,name,price,now)`、`mark_failed(probe,country,reason,now)`、`probe_load()→{available,failed}`、候选项 `{country,name,price}`、probe dict `{available:[{country,name,price,last_ok}], failed:{country:{reason,last_fail}}}` 全程一致；前端 `gmailCfg.auto_probe` 随 gmail_sms_config 存、可用库读 gmail_country_probe。✅
