# Google 接码多平台级联配置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** google 注册接码可在前端选平台→拉国家/价格→选国家→配价格上限/固定档（全局存 DB），接码走 services sms_service。

**Architecture:** 各 provider 加 `get_prices(service)` 查价；sms_service 暴露 `/prices` 路由；config_service 存 `gmail_sms_config`；`browser_phone_and_finalize` 改走 services 取号/取码；前端 SmsConfigPage 加级联块。

**Tech Stack:** Python 3.13 · httpx · pytest(asyncio_mode=auto) · React/antd/vitest · SQLAlchemy(JSON 列)

**约定：** pytest/python 在 `f:/reg-factory/services` 跑（pythonpath=["."]）；前端在 `f:/reg-factory/frontend`。参考 spec `docs/superpowers/specs/2026-06-13-gmail-sms-config-design.md`。

**已实测的 API 形状（直接用，勿重查）：**
- hero_sms/sms_bower：`GET {base}?api_key=K&action=getPrices&service=go` → `{"52":{"go":{"cost":0.1,"count":12112}}, ...}`
- sms_cloud：`GET {base}/public/sms/getInventory?serviceCode=go`（header apiKey）→ `{"code":0,"data":[{"country":187,"countryName":"美国","count":287628,"retailPrice":12.00,"freePriceMap":{...}}]}`；国家名另在 `/public/sms/countries`（已含 countryName，无需再查）
- config value 是 JSON 列：`ConfigService.set(key, value: dict)` 直接存 dict；`get(key).value` 取回 dict
- services 取号：`POST /sms/number/acquire {service,country,provider}`；取码：`GET /sms/number/{id}/code`

---

## File Structure

- `sms_service/providers/base.py` — `SMSProvider` 加 `get_prices` 抽象 + `get_number` 加 `max_price/fixed_price` 参数
- `sms_service/providers/sms_activate_base.py` — `get_prices`(getPrices)、`get_number` 透传价格
- `sms_service/providers/sms_cloud.py` — `get_prices`(getInventory)、`get_number` 透传价格
- `sms_service/service.py` — `get_prices` 编排
- `sms_service/schemas.py` — `AcquireRequest` 加 `max_price/fixed_price`
- `sms_service/main.py` — `GET /sms/providers/{name}/prices` 路由 + acquire 透传价格
- `register_gmail_hybrid.py` — `browser_phone_and_finalize` 接 services 取号/取码
- `services/worker/flows/gmail.py` — `_step_phone_verify` 传 sms_config
- `services/gateway/routers/registration.py` — `/register/google` 读 `gmail_sms_config` 注入
- `frontend/src/pages/SmsConfigPage.tsx` — Google 接码级联块
- Tests: `tests/sms_service/test_provider_prices.py`、`tests/sms_service/test_sms_routes.py`(扩)、`tests/sms_service/test_acquire_price.py`、`tests/gateway/test_registration_routes.py`(扩)

---

## Task 1: provider `get_prices` —— 基类抽象 + sms_activate(getPrices)

**Files:** Modify `sms_service/providers/base.py`、`sms_service/providers/sms_activate_base.py`；Create `tests/sms_service/test_provider_prices.py`

- [ ] **Step 1: 失败测试**

`tests/sms_service/test_provider_prices.py`：
```python
import httpx
import pytest
from sms_service.providers.sms_activate_base import SmsActivateProvider


def patch_http(monkeypatch, handler):
    real = httpx.AsyncClient
    def fake(*a, **kw):
        kw.pop("transport", None)
        return real(*a, transport=httpx.MockTransport(handler), **kw)
    monkeypatch.setattr(httpx, "AsyncClient", fake)


class _P(SmsActivateProvider):
    name = "testp"
    _default_base_url = "https://x.test/handler_api.php"


async def test_sms_activate_get_prices(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, json={
        "52": {"go": {"cost": 0.1, "count": 12112}},
        "4": {"go": {"cost": 0.025, "count": 500}},
    }))
    rows = await _P({"api_key": "K"}).get_prices("go")
    # 按 cost 升序：4(0.025) 在 52(0.1) 前
    assert rows[0]["country"] == "4" and rows[0]["cost"] == 0.025 and rows[0]["count"] == 500
    assert rows[1]["country"] == "52" and rows[1]["cost"] == 0.1
```

- [ ] **Step 2: 跑红** `cd f:/reg-factory/services && python -m pytest tests/sms_service/test_provider_prices.py -v` → FAIL（get_prices 未定义/AttributeError）

- [ ] **Step 3: 实现** base.py 加抽象（在 `get_countries` 后）：
```python
    async def get_prices(self, service: str) -> list[dict[str, Any]]:
        """返回该 service 各国价格/库存：[{country, country_name?, cost, count}]，按 cost 升序。"""
        return []
```
sms_activate_base.py 加：
```python
    async def get_prices(self, service: str) -> list:
        text = await self._request({"action": "getPrices", "service": service})
        import json as _json
        data = _json.loads(text) if text.strip().startswith("{") else {}
        rows = []
        for cid, svc in data.items():
            info = svc.get(service) if isinstance(svc, dict) else None
            if info and "cost" in info:
                rows.append({"country": str(cid), "cost": float(info["cost"]), "count": int(info.get("count", 0))})
        rows.sort(key=lambda r: r["cost"])
        return rows
```
注意：`_request` 返回 `resp.text`（sms_activate 是纯文本/JSON 混合），getPrices 返回 JSON 文本，故 `json.loads`。

- [ ] **Step 4: 跑绿** 同 Step 2 命令 → PASS

- [ ] **Step 5: Commit**
```bash
cd f:/reg-factory && git add services/sms_service/providers/base.py services/sms_service/providers/sms_activate_base.py services/tests/sms_service/test_provider_prices.py && git commit -m "feat(sms): provider get_prices 抽象 + sms_activate getPrices 查价"
```

---

## Task 2: sms_cloud `get_prices`(getInventory)

**Files:** Modify `sms_service/providers/sms_cloud.py`；Modify `tests/sms_service/test_provider_prices.py`

- [ ] **Step 1: 追加失败测试**
```python
from sms_service.providers.sms_cloud import SmsCloudProvider


async def test_sms_cloud_get_prices(monkeypatch):
    patch_http(monkeypatch, lambda req: httpx.Response(200, json={"code": 0, "data": [
        {"country": 187, "countryName": "美国", "count": 287628, "retailPrice": 12.0},
        {"country": 4, "countryName": "菲律宾", "count": 100, "retailPrice": 0.3},
    ]}))
    rows = await SmsCloudProvider({"api_key": "K", "base_url": "https://smscloud.sbs/api/system"}).get_prices("go")
    assert rows[0]["country"] == "4" and rows[0]["cost"] == 0.3 and rows[0]["country_name"] == "菲律宾"
    assert rows[1]["country"] == "187" and rows[1]["cost"] == 12.0
```

- [ ] **Step 2: 跑红** `python -m pytest tests/sms_service/test_provider_prices.py::test_sms_cloud_get_prices -v` → FAIL

- [ ] **Step 3: 实现** sms_cloud.py 加（用已有 `_get` helper，它已解 `{code,message,data}` 信封返回 data）：
```python
    async def get_prices(self, service: str) -> list:
        # getInventory 返回的是 data 列表（_get 已解信封）；retailPrice=零售价，count=库存
        data = await self._get("/public/sms/getInventory", {"serviceCode": service})
        rows = data if isinstance(data, list) else []
        out = [{
            "country": str(r["country"]),
            "country_name": r.get("countryName", ""),
            "cost": float(r.get("retailPrice", 0)),
            "count": int(r.get("count", 0)),
        } for r in rows if "country" in r]
        out.sort(key=lambda r: r["cost"])
        return out
```
注意：`_get` 返回 `body["data"]`（list），故 `data` 直接是列表。

- [ ] **Step 4: 跑绿** → PASS

- [ ] **Step 5: Commit**
```bash
cd f:/reg-factory && git add services/sms_service/providers/sms_cloud.py services/tests/sms_service/test_provider_prices.py && git commit -m "feat(sms_cloud): get_prices 用 getInventory 查国家/价格/库存"
```

---

## Task 3: service.get_prices + `GET /sms/providers/{name}/prices` 路由

**Files:** Modify `sms_service/service.py`、`sms_service/main.py`；Modify `tests/sms_service/test_sms_routes.py`

- [ ] **Step 1: 失败测试** 在 `tests/sms_service/test_sms_routes.py` 追加（用现有 conftest 的 FakeSmsService + client）：
```python
def test_get_prices_route(client, monkeypatch):
    from sms_service.main import app, get_service
    class _Svc:
        async def get_prices(self, name, service):
            return [{"country": "52", "cost": 0.1, "count": 100}]
    app.dependency_overrides[get_service] = lambda: _Svc()
    r = client.get("/sms/providers/hero_sms/prices?service=go")
    app.dependency_overrides.pop(get_service, None)
    assert r.status_code == 200
    assert r.json()["data"][0]["country"] == "52"
```

- [ ] **Step 2: 跑红** `python -m pytest tests/sms_service/test_sms_routes.py::test_get_prices_route -v` → FAIL(404)

- [ ] **Step 3: 实现** service.py 加：
```python
    async def get_prices(self, provider_name: str, service: str) -> list:
        provider = await self._get_provider(provider_name)
        return await provider.get_prices(service)
```
main.py 加路由（在 balance 路由后）：
```python
@app.get("/sms/providers/{name}/prices", response_model=ApiResponse)
async def get_prices(name: str, service: str = "go", svc: SmsService = Depends(get_service)):
    from fastapi import HTTPException
    try:
        return ApiResponse(data=await svc.get_prices(name, service))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 4: 跑绿** → PASS

- [ ] **Step 5: Commit**
```bash
cd f:/reg-factory && git add services/sms_service/service.py services/sms_service/main.py services/tests/sms_service/test_sms_routes.py && git commit -m "feat(sms): GET /sms/providers/{name}/prices 路由查价"
```

---

## Task 4: `get_number` + acquire 透传 max_price/fixed_price

**Files:** Modify `sms_service/providers/base.py`、`sms_activate_base.py`、`sms_cloud.py`、`schemas.py`、`service.py`、`main.py`；Create `tests/sms_service/test_acquire_price.py`

- [ ] **Step 1: 失败测试** `tests/sms_service/test_acquire_price.py`：
```python
import httpx
from sms_service.providers.sms_activate_base import SmsActivateProvider


def patch_http(monkeypatch, handler):
    real = httpx.AsyncClient
    def fake(*a, **kw):
        kw.pop("transport", None)
        return real(*a, transport=httpx.MockTransport(handler), **kw)
    monkeypatch.setattr(httpx, "AsyncClient", fake)


class _P(SmsActivateProvider):
    name = "testp"
    _default_base_url = "https://x.test/handler_api.php"


async def test_get_number_passes_price(monkeypatch):
    captured = {}
    def handler(req):
        captured["params"] = dict(req.url.params)
        return httpx.Response(200, text="ACCESS_NUMBER:12345:66812345678")
    patch_http(monkeypatch, handler)
    await _P({"api_key": "K"}).get_number("go", "52", max_price="0.2", fixed_price=False)
    assert captured["params"].get("maxPrice") == "0.2"
    assert "fixedPrice" not in captured["params"]  # fixed_price=False 不带
```

- [ ] **Step 2: 跑红** `python -m pytest tests/sms_service/test_acquire_price.py -v` → FAIL（get_number 不接 max_price）

- [ ] **Step 3: 实现**
base.py `get_number` 抽象签名改：
```python
    async def get_number(self, service: str, country: str, max_price: str = "0", fixed_price: bool = False) -> AcquireResult:
        ...
```
sms_activate_base.py `get_number`：
```python
    async def get_number(self, service: str, country: str, max_price: str = "0", fixed_price: bool = False) -> AcquireResult:
        params = {"action": "getNumber", "service": service, "country": country}
        if max_price and str(max_price) not in ("0", "0.0", ""):
            params["maxPrice"] = str(max_price)
            if fixed_price:
                params["fixedPrice"] = "true"
        text = await self._request(params)
        if not text.startswith("ACCESS_NUMBER"):
            raise ValueError(f"{self.name} getNumber failed: {text}")
        parts = text.split(":")
        return AcquireResult(order_id=parts[1], phone_number=parts[2], provider=self.name)
```
sms_cloud.py `get_number` 加同签名（sms_cloud 价格在 inventory，getNumber 不一定接 maxPrice；保持忽略 price 参数即可，签名兼容）：
```python
    async def get_number(self, service: str, country: str, max_price: str = "0", fixed_price: bool = False) -> AcquireResult:
        data = await self._get("/public/sms/getNumber", {"serviceCode": service, "countryCode": country})
        return AcquireResult(order_id=str(data["id"]), phone_number=data["phoneNumber"], provider=self.name)
```
schemas.py `AcquireRequest` 加：
```python
    max_price: str = "0"
    fixed_price: bool = False
```
service.py `acquire_number` 传：
```python
    async def acquire_number(self, service, country, provider_name=None, max_price="0", fixed_price=False):
        provider = await self._get_provider(provider_name) if provider_name else await self._select_best_provider()
        result = await provider.get_number(service, country, max_price=max_price, fixed_price=fixed_price)
        await self._order_repo.create(provider=provider.name, service=service, country=country,
            phone_number=result.phone_number, order_id_external=result.order_id, status=OrderStatus.PENDING)
        return result
```
main.py acquire 端点传 `body.max_price, body.fixed_price`：
```python
        result = await service.acquire_number(body.service, body.country, body.provider, body.max_price, body.fixed_price)
```

- [ ] **Step 4: 跑绿** `python -m pytest tests/sms_service/test_acquire_price.py tests/sms_service/test_sms_cloud_provider.py tests/sms_service/test_sms_activate_base.py -v` → 全 PASS（旧取号测试因默认参数仍绿）

- [ ] **Step 5: Commit**
```bash
cd f:/reg-factory && git add services/sms_service/providers/base.py services/sms_service/providers/sms_activate_base.py services/sms_service/providers/sms_cloud.py services/sms_service/schemas.py services/sms_service/service.py services/sms_service/main.py services/tests/sms_service/test_acquire_price.py && git commit -m "feat(sms): 取号透传 maxPrice/fixedPrice(get_number+acquire 扩参)"
```

---

## Task 5: browser_phone_and_finalize 接入 services 取号/取码

**Files:** Modify `register_gmail_hybrid.py`

- [ ] **Step 1: 加 services 接码 helper**（在 `browser_phone_and_finalize` 前的模块级）：
```python
def _svc_acquire(provider, country, max_price, fixed, service="go"):
    """走 services sms_service 取号。返回 (phone, order_id) 或 (None, None)。"""
    import requests as _r
    try:
        resp = _r.post("http://localhost:8001/sms/number/acquire", json={
            "service": service, "country": str(country), "provider": provider,
            "max_price": str(max_price), "fixed_price": bool(fixed),
        }, timeout=30, proxies={"http": None, "https": None})
        d = resp.json().get("data") or {}
        return d.get("phone_number"), d.get("order_id")
    except Exception as e:
        print(f"  [svc-sms] acquire err: {e}")
        return None, None


def _svc_code(order_id, max_wait=180):
    import requests as _r
    try:
        resp = _r.get(f"http://localhost:8001/sms/number/{order_id}/code", params={"timeout": max_wait},
                      timeout=max_wait + 10, proxies={"http": None, "https": None})
        return (resp.json().get("data") or {}).get("code")
    except Exception as e:
        print(f"  [svc-sms] code err: {e}")
        return None
```

- [ ] **Step 2: browser_phone_and_finalize 签名 + 取号改造**（258 区域）：
把 `async def browser_phone_and_finalize(page, profile, ctx=None, profile_id=None):` 改为加 `sms_config: dict | None = None`；在取 hero_svc/max_price/... 后加分支：当 `sms_config` 有 `provider` 时走 services，否则保持旧 common/sms.py。
```python
    sms_config = sms_config or {}
    use_svc = bool(sms_config.get("provider"))
    svc_provider = sms_config.get("provider", "")
    svc_country = sms_config.get("country", hero_country)
    svc_maxprice = sms_config.get("max_price", max_price)
    svc_fixed = sms_config.get("fixed_price", fixed)
```
在取号处（`raw, cc, pkey = sms.get_phone(...)`）改为：
```python
            if use_svc:
                e164_raw, order_id = _svc_acquire(svc_provider, svc_country, svc_maxprice, svc_fixed)
                if not e164_raw:
                    raise RuntimeError("svc acquire 无号")
                raw, cc, pkey = e164_raw, "", f"svc_{order_id}"
            else:
                raw, cc, pkey = sms.get_phone("", hero_svc, max_price=max_price, hero_country=hero_country, hero_fixed_price=fixed)
```
在收码处（`sms.get_code(pkey, ...)`）改为：当 `pkey.startswith("svc_")` 用 `_svc_code(pkey[4:], code_wait)`，否则旧 `sms.get_code`。释放同理（services `POST /sms/number/{id}/cancel`）。

- [ ] **Step 3: 编译校验**
Run: `cd f:/reg-factory && python -m py_compile register_gmail_hybrid.py`
Expected: 无报错（浏览器自动化无单测，靠编译 + 实跑验证）

- [ ] **Step 4: Commit**
```bash
cd f:/reg-factory && git add register_gmail_hybrid.py && git commit -m "feat(gmail-reg): browser_phone_and_finalize 接 services 取号/取码(sms_config 有 provider 时)"
```

---

## Task 6: gmail flow 传 sms_config

**Files:** Modify `services/worker/flows/gmail.py`

- [ ] **Step 1: 改 _step_phone_verify**（62 行 browser_phone_and_finalize 调用）：
```python
        result = await browser_phone_and_finalize(page, profile, ctx=ctx, profile_id=pid,
                                                  sms_config=context.get("config", {}).get("sms"))
```

- [ ] **Step 2: 编译** `cd f:/reg-factory/services && python -m py_compile worker/flows/gmail.py` → OK

- [ ] **Step 3: Commit**
```bash
cd f:/reg-factory && git add services/worker/flows/gmail.py && git commit -m "feat(gmail-flow): _step_phone_verify 传 sms_config 给接码"
```

---

## Task 7: /register/google 读 gmail_sms_config 注入

**Files:** Modify `services/gateway/routers/registration.py`；Modify `tests/gateway/test_registration_routes.py`

- [ ] **Step 1: 失败测试** 追加（mock httpx 读 config + task_manager）：
```python
def test_register_google_injects_sms_config(client):
    import httpx
    from unittest.mock import AsyncMock, MagicMock
    captured = {}
    def fake_submit(**kwargs):
        captured.update(kwargs); return "tid"
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"data": {"value": {"provider": "hero_sms", "country": "52", "max_price": "0.2", "fixed_price": False}}}
    fake_client = AsyncMock(); fake_client.get = AsyncMock(return_value=fake_resp)
    fake_ctx = MagicMock(); fake_ctx.__aenter__ = AsyncMock(return_value=fake_client); fake_ctx.__aexit__ = AsyncMock(return_value=False)
    with patch("gateway.routers.registration._pick_active_proxy", new_callable=AsyncMock, return_value=""), \
         patch("gateway.routers.registration._httpx.AsyncClient", return_value=fake_ctx), \
         patch("worker.process_manager.task_manager") as mock_tm:
        mock_tm.submit.side_effect = fake_submit
        r = client.post("/register/google", json={"count": 1})
    assert r.status_code == 200
    assert captured["config"]["sms"]["provider"] == "hero_sms"
```
（顶部加 `from gateway.routers import registration` 不需要；patch 路径用 `gateway.routers.registration._httpx`，故 registration.py 要 `import httpx as _httpx`。）

- [ ] **Step 2: 跑红** `python -m pytest tests/gateway/test_registration_routes.py::test_register_google_injects_sms_config -v` → FAIL

- [ ] **Step 3: 实现** registration.py 顶部加 `import httpx as _httpx` + `from gateway.deps import _CONFIG_URL`；端点内 platform=="google" 时读 config：
```python
    if platform == "google":
        try:
            async with _httpx.AsyncClient(timeout=5, trust_env=False) as c:
                r = await c.get(f"{_CONFIG_URL}/config/gmail_sms_config")
                val = (r.json().get("data") or {}).get("value")
                if isinstance(val, dict):
                    config["sms"] = val
        except Exception:
            pass
```
（放在 `if not proxy:` 前。`_CONFIG_URL` 已在 gateway.deps 定义。）

- [ ] **Step 4: 跑绿** `python -m pytest tests/gateway/test_registration_routes.py -v` → 全 PASS

- [ ] **Step 5: Commit**
```bash
cd f:/reg-factory && git add services/gateway/routers/registration.py services/tests/gateway/test_registration_routes.py && git commit -m "feat(register): /register/google 读 gmail_sms_config 注入 config[sms]"
```

---

## Task 8: 前端 SmsConfigPage「Google 注册接码」级联块

**Files:** Modify `frontend/src/pages/SmsConfigPage.tsx`；Create `frontend/src/pages/SmsConfigPage.gmail.test.tsx`

- [ ] **Step 1: 失败测试** `SmsConfigPage.gmail.test.tsx`（mock fetch：providers/config/prices）：
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '@/test/utils'
import SmsConfigPage from './SmsConfigPage'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn((url: string) => {
    if (url.includes('/providers')) return Promise.resolve({ json: () => Promise.resolve({ data: [{ name: 'hero_sms', display_name: 'HeroSMS' }] }) })
    if (url.includes('/sms/config')) return Promise.resolve({ json: () => Promise.resolve({ data: [] }) })
    if (url.includes('/config/gmail_sms_config')) return Promise.resolve({ json: () => Promise.resolve({ data: { value: { provider: 'hero_sms', country: '52', max_price: '0.2', fixed_price: false } } }) })
    if (url.includes('/prices')) return Promise.resolve({ json: () => Promise.resolve({ data: [{ country: '52', cost: 0.1, count: 100 }] }) })
    return Promise.resolve({ json: () => Promise.resolve({ data: [] }) })
  }))
})

describe('SmsConfigPage Google 接码块', () => {
  it('渲染 Google 注册接码标题', async () => {
    renderWithProviders(<SmsConfigPage />)
    await waitFor(() => expect(screen.getByText(/Google 注册接码/)).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: 跑红** `cd f:/reg-factory/frontend && npx vitest run src/pages/SmsConfigPage.gmail.test.tsx` → FAIL（无该文本）

- [ ] **Step 3: 实现** SmsConfigPage.tsx 在现有内容末尾（Spin 内、表格后）加一个 Card。新增 state + effect + 组件：
```tsx
// 顶部 state（与现有 state 并列）
const [gmailCfg, setGmailCfg] = useState<{provider:string;country:string;max_price:string;fixed_price:boolean}>({ provider: 'hero_sms', country: '', max_price: '0.2', fixed_price: false })
const [gmailPrices, setGmailPrices] = useState<{country:string;cost:number;count:number;country_name?:string}[]>([])

// 加载已存配置
useEffect(() => {
  fetch('/api/config/gmail_sms_config').then(r => r.json()).then(res => {
    if (res.data?.value) setGmailCfg(res.data.value)
  }).catch(() => {})
}, [])

// 选平台 → 拉价
const loadPrices = (provider: string) => {
  fetch(`/api/sms/providers/${provider}/prices?service=go`).then(r => r.json())
    .then(res => setGmailPrices(res.data || [])).catch(() => setGmailPrices([]))
}

const saveGmailCfg = () => {
  fetch('/api/config/gmail_sms_config', {
    method: 'PUT', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('token')}` },
    body: JSON.stringify({ value: gmailCfg }),
  }).then(r => r.json()).then(res => {
    if (res.success === false) message.error(res.message || '保存失败')
    else message.success('已保存')
  })
}
```
JSX（表格 Card 后加）：
```tsx
<Card title="Google 注册接码" style={{ marginTop: 16 }}>
  <Form layout="inline">
    <Form.Item label="平台">
      <Select style={{ width: 140 }} value={gmailCfg.provider}
        onChange={(v) => { setGmailCfg({ ...gmailCfg, provider: v }); loadPrices(v) }}
        options={providers.map(p => ({ value: p.name, label: p.display_name || p.name }))} />
    </Form.Item>
    <Form.Item label="国家">
      <Select style={{ width: 220 }} value={gmailCfg.country} showSearch
        onChange={(v) => { const row = gmailPrices.find(r => r.country === v); setGmailCfg({ ...gmailCfg, country: v, max_price: row ? String(row.cost) : gmailCfg.max_price }) }}
        options={gmailPrices.map(r => ({ value: r.country, label: `${r.country_name || r.country} / ${r.cost} / 库存${r.count}` }))} />
    </Form.Item>
    <Form.Item label="价格上限"><InputNumber min={0} step={0.1} value={Number(gmailCfg.max_price)} onChange={(v) => setGmailCfg({ ...gmailCfg, max_price: String(v ?? 0) })} /></Form.Item>
    <Form.Item label="固定价格"><Switch checked={gmailCfg.fixed_price} onChange={(v) => setGmailCfg({ ...gmailCfg, fixed_price: v })} /></Form.Item>
    <Button type="primary" onClick={saveGmailCfg}>保存</Button>
  </Form>
</Card>
```
（确保 import 含 Card/Form/Select/InputNumber/Switch/Button/message——现有已 import 大部分，补 Card/Select。）

- [ ] **Step 4: 跑绿** `npx vitest run src/pages/SmsConfigPage.gmail.test.tsx` → PASS；再 `npx tsc --noEmit` 无误

- [ ] **Step 5: Commit**
```bash
cd f:/reg-factory && git add frontend/src/pages/SmsConfigPage.tsx frontend/src/pages/SmsConfigPage.gmail.test.tsx && git commit -m "feat(frontend): SmsConfigPage 加 Google 接码级联块(平台→国家/价格→存配置)"
```

---

## Task 9: 联网 smoke + 默认配置兜底

**Files:** Create `services/scripts/gmail_sms_prices_smoke.py`；Modify `.env`

- [ ] **Step 1: smoke 脚本** `services/scripts/gmail_sms_prices_smoke.py`：用 DB key 实跑三家 get_prices("go")，打印前 3 便宜国家。
```python
import asyncio, json, sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sms_service.providers.base import ProviderRegistry
import sms_service.providers.sms_cloud, sms_service.providers.hero_sms, sms_service.providers.sms_bower  # noqa


def _cfg(name):
    con = sqlite3.connect(str(Path(__file__).resolve().parents[1] / "sms.db"))
    r = con.execute("SELECT config FROM sms_platform_configs WHERE provider_name=?", (name,)).fetchone()
    return json.loads(r[0]) if r else None


async def main():
    for name in ("hero_sms", "sms_bower", "sms_cloud"):
        cfg = _cfg(name)
        if not cfg:
            print(name, "未配置"); continue
        try:
            rows = await ProviderRegistry.get(name, cfg).get_prices("go")
            print(f"{name}: {len(rows)} 国, 最便宜3: {rows[:3]}")
        except Exception as e:
            print(f"{name}: ERR {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 跑 smoke** `cd f:/reg-factory/services && python scripts/gmail_sms_prices_smoke.py` → 三家各打印便宜国家列表（联网，失败重跑）

- [ ] **Step 3: .env 默认兜底** 改 `.env:106` `SMS_MAXPRICE_GMAIL=5` → `0.2`，并在该行后加 `SMS_HERO_FIXED_PRICE=false`（无 DB 配置时旧链路也能买 0.1 泰国号）

- [ ] **Step 4: Commit**
```bash
cd f:/reg-factory && git add services/scripts/gmail_sms_prices_smoke.py .env && git commit -m "test(sms): get_prices 联网 smoke + .env 接码默认兜底改 0.2/false"
```

---

## Task 10: 重启 gateway/sms + 端到端验证

- [ ] **Step 1: 重启 sms_service + gateway**（加载新路由/端点）
```
# 杀 8001/8000(PowerShell Stop-Process)，按 services-db-per-service 启动:
DATABASE_URL="sqlite+aiosqlite:///sms.db" python -m uvicorn sms_service.main:app --host 127.0.0.1 --port 8001 --workers 1 --log-level warning
DATABASE_URL="sqlite+aiosqlite:///gateway.db" SMS_SERVICE_URL=... ACCOUNT_SERVICE_URL=... CONFIG_SERVICE_URL=... python -m uvicorn gateway.main:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info
```

- [ ] **Step 2: 验证 /prices 路由**
Run: `curl -s "http://localhost:8000/sms/providers/hero_sms/prices?service=go" | head -c 200`
Expected: `{"success":true,"data":[{"country":...,"cost":...,"count":...}]}`

- [ ] **Step 3: 验证 config 存取**
Run: `curl -s -X PUT "http://localhost:8000/config/gmail_sms_config" -H "Content-Type: application/json" -d '{"value":{"provider":"hero_sms","country":"52","max_price":"0.2","fixed_price":false}}'` 然后 `curl -s "http://localhost:8000/config/gmail_sms_config"`
Expected: GET 返回 value 含 provider hero_sms

- [ ] **Step 4: 前端实测** 前端 SmsConfigPage 选平台→看国家/价格下拉→选国家→保存；再 Google 页 count=1 注册，看接码是否走 services（日志 `[svc-sms] acquire`）拿到号

- [ ] **Step 5: 全量回归**
Run: `cd f:/reg-factory/services && python -m pytest tests/sms_service/ tests/gateway/test_registration_routes.py -q`
Expected: 全 PASS

---

## Self-Review

**1. Spec coverage：** ①provider get_prices→T1/T2；②/prices 路由→T3；③接码接入 services→T4(价格透传)+T5(browser_phone)+T6(flow);④前端级联→T8；⑤链路→T7；配置存取→T7(读)+T8(写)+T10(验证)；默认兜底→T9。✅
**2. Placeholder：** 每 step 含完整代码/命令。T5 浏览器改造给了 helper + 改造点（取号/收码/释放分支），无 mock 测试因属浏览器自动化（编译+smoke+实测验证），已说明。✅
**3. 类型一致：** `get_prices(service)->[{country,country_name?,cost,count}]`、`get_number(service,country,max_price,fixed_price)`、`AcquireRequest{...,max_price,fixed_price}`、config value=dict、`config["sms"]={provider,country,max_price,fixed_price}` 全程一致。`_get` 返回 data(sms_cloud)、`_request` 返回 text(sms_activate) 的差异已在 T1/T2 注明。✅
