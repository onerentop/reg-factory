# SMS-Activate 系 Provider（hero_sms / sms_bower）对齐官方 API 修复设计

- 日期：2026-06-13
- 主诉：继续修 sms_bower 和 hero（接续 sms_cloud 修复）
- 文档：`C:\Users\lenovo\Downloads\api\hero.json`(OpenAPI)、`C:\Users\lenovo\Downloads\api\SmsBower Activations API.html`(Postman)
- 范围（已确认）：**抽 `SmsActivateProvider` 基类，hero_sms + sms_bower 共用**

## 1. 根因（已用真实密钥实跑验证）

两家平台都兼容 **SMS-Activate `handler_api.php` 纯文本协议**（行业标准）：`GET {base_url}?api_key=X&action=Y` → `ACCESS_*` / `STATUS_*` 纯文本。

| Provider | 现状代码 | 实跑结果 | 判定 |
|---|---|---|---|
| `hero_sms` | handler_api + query `api_key` + `getBalance` | `ACCESS_BALANCE:1.1947` | ✅ 现状协议正确，但**无单元测试** |
| `sms_bower` | REST `smsbower.com/api/balance` + `Bearer` token + JSON | HTTP **404** `route api/balance could not be found` | ❌ 端点不存在，协议全错 |
| `sms_bower`（正确协议）| `smsbower.com/stubs/handler_api.php?api_key=&action=getBalance` | `ACCESS_BALANCE:0.784` | ✅ 真实余额 0.784 |

文档核对：SmsBower 文档真实端点为 `/stubs/handler_api.php?api_key=`，action 含 `getNumber`/`getStatus`，响应 token `ACCESS_NUMBER`/`STATUS_OK`——与 hero/标准 sms-activate **完全一致**。

改完后两家代码几乎相同 → 抽公共基类（模板方法），消除重复。

## 2. 正确协议（SMS-Activate handler_api，两家共用）

全部 `GET {base_url}?api_key=<key>&action=<action>[&...]`，返回纯文本：

| 方法 | action + 参数 | 成功返回 | 解析 |
|---|---|---|---|
| `get_balance` | `getBalance` | `ACCESS_BALANCE:1.1947` | `float(text.split(":")[1])` |
| `get_number` | `getNumber&service=<s>&country=<c>` | `ACCESS_NUMBER:<id>:<phone>` | `parts[1]`=order_id, `parts[2]`=phone |
| `get_code`(轮询) | `getStatus&id=<id>` | `STATUS_OK:<code>`（已收到）/ `STATUS_WAIT_CODE`（等待）/ `STATUS_CANCEL`（取消）| `STATUS_OK`→`split(":")[1]` |
| `complete` | `setStatus&id=<id>&status=6` | `ACCESS_ACTIVATION` 等（不解析）| 仅发请求 |
| `cancel` | `setStatus&id=<id>&status=8` | `ACCESS_CANCEL` 等（不解析）| 仅发请求 |

base_url：hero=`https://hero-sms.com/stubs/handler_api.php`，sms_bower=`https://smsbower.com/stubs/handler_api.php`。

## 3. 改动设计

### 3.1 新建 `services/sms_service/providers/sms_activate_base.py`（模板方法基类）

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

### 3.2 重写 `services/sms_service/providers/hero_sms.py`（继承基类，行为不变）

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

### 3.3 重写 `services/sms_service/providers/sms_bower.py`（继承基类，从 REST 改对）

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

### 3.4 修 DB 数据（sms_bower base_url）

`sms.db` 里 sms_bower 现存 `base_url=https://smsbower.com/api`（错），会覆盖代码默认值（`config.get("base_url", default)` 优先 DB）。一次性脚本读出 config、**只改 base_url、保留 api_key**、写回：

```python
# services/scripts/fix_sms_bower_baseurl.py 核心逻辑
con = sqlite3.connect("sms.db")
row = con.execute("SELECT config FROM sms_platform_configs WHERE provider_name='sms_bower'").fetchone()
cfg = json.loads(row[0])
cfg["base_url"] = "https://smsbower.com/stubs/handler_api.php"
con.execute("UPDATE sms_platform_configs SET config=? WHERE provider_name='sms_bower'", (json.dumps(cfg),))
con.commit()
```

hero_sms DB base_url 已对，不动。

## 4. 测试方案

**单元测试** `services/tests/sms_service/test_sms_activate_base.py`（httpx.MockTransport mock 纯文本，离线）：

测试桩（隔离基类逻辑，不依赖具体平台）：
```python
class _P(SmsActivateProvider):
    name = "testp"
    _default_base_url = "https://x.test/handler_api.php"
```

| 用例 | mock 返回 | 断言 |
|---|---|---|
| balance 解析 | `ACCESS_BALANCE:1.1947` | `== 1.1947` |
| balance 错误 | `BAD_KEY` | 抛 `ValueError` 含 `BAD_KEY` |
| 请求带 api_key+action | `ACCESS_BALANCE:1` | request.url.params 含 `api_key`/`action=getBalance` |
| get_number 解析 | `ACCESS_NUMBER:12345:79001234567` | order_id=`12345`,phone=`79001234567`,params 含 `service`/`country` |
| get_number 错误 | `NO_NUMBERS` | 抛 `ValueError` |
| get_code 命中 | `STATUS_OK:654321` | code=`654321`,status=RECEIVED,params 含 `action=getStatus`/`id` |
| get_code 取消 | `STATUS_CANCEL` | code=None,status=CANCELLED |
| get_code 超时 | `STATUS_WAIT_CODE`（monkeypatch asyncio.sleep）| status=TIMEOUT |
| complete 端点 | `ACCESS_ACTIVATION` | params 含 `action=setStatus`/`id`/`status=6` |
| cancel 端点 | `ACCESS_CANCEL` | params 含 `action=setStatus`/`id`/`status=8` |

**子类配置测** `services/tests/sms_service/test_sms_activate_subclasses.py`：
- hero/sms_bower 经 `ProviderRegistry.get(name, {"api_key":"k"})` 实例化，断言 `_base_url` == 各自 handler_api.php 默认值、`display_name` 正确。

**联网 smoke** `services/scripts/sms_activate_smoke.py`：用 sms.db 真实 key，hero + sms_bower 各打 getBalance，断言返回非负 float（实测 hero≈1.19、bower≈0.78）。手动运行，不进 CI。

## 5. 非目标

- 不改 sms_cloud（不同协议，已修）、不改 `base.py` 接口、不改 `service.py`。
- 不实现 getNumberV(V2 JSON 取号)、emails、offers 等额外 action（YAGNI）。
- 不动前端（修好后余额自然正确显示）。
- service/country 编码体系是数据层面，provider 透传，不在本次范围。
