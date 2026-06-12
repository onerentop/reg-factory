# SMS Cloud Provider 对齐官方 API 修复设计

- 日期：2026-06-13
- 主诉：接码平台 sms_cloud「查询余额不对」（密钥已配置，余额显示 0/错）
- 范围（已确认）：**整个 `SmsCloudProvider` 按官方文档重写**——鉴权/取号/取码/取消/完成全错，不只余额

## 1. 根因（已用真实密钥实跑验证）

现有 `services/sms_service/providers/sms_cloud.py` 与官方 API（文档：`C:\Users\lenovo\Downloads\api\SMS Cloud API.html`，docsify 渲染的「SMS Cloud 对外开放API v1.0.0」）**三处全错**：

| 维度 | 现状 ❌ | 文档正确 ✅ |
|---|---|---|
| 鉴权 | query `?api_key=<key>` | **HTTP Header `apiKey: <key>`** |
| 余额端点 | `GET /get_balance` | `GET /public/sms/balance` |
| 响应解析 | 顶层 `result["balance"]` | 信封 `{code,message,data}`，取 `data.balance`，且判 `code==0` |

实跑证据：
- 错误传法（query api_key 等 8 种变体）→ 全返回 `{"code":40001,"message":"登录凭证已过期，请重新登录","data":null}`；代码 `result.get("balance",0)` 取不到键 → 静默返回 **0**（这就是"余额不对"）。
- 正确传法 `GET https://smscloud.sbs/api/system/public/sms/balance` + header `apiKey` → `{"code":0,"message":"操作成功","data":{"balance":8.0}}`，**真实余额 8.0 钻石**。

`base_url=https://smscloud.sbs/api/system` 是对的，DB 配置（`sms.db` 的 `sms_platform_configs`）和 `config_schema` 默认值都**保留不变**。

## 2. 完整正确协议（全部 GET + header `apiKey` + `{code,message,data}` 信封；data 在成功时 `code==0`）

| 方法 | 端点 | 入参 | 成功 `data` 字段 |
|---|---|---|---|
| `get_balance` | `/public/sms/balance` | 无 | `balance`(number) |
| `get_number` | `/public/sms/getNumber` | query `serviceCode`(string), `countryCode`(int) | `id`(订单ID,string), `phoneNumber`, `serviceCode`, `countryCode`, `countryPhoneCode`, `creditAmount`, `activationTime`, `activationEndTime` |
| `get_code`（轮询） | `/public/sms/orders/sync/{id}` | path `id` | `id`, `code`(验证码,空=未到), `text`(原文), `dateTime` |
| `cancel` | `/public/sms/orders/cancel/{id}` | path `id` | `{}` |
| `complete` | `/public/sms/orders/finish/{id}` | path `id` | `{}` |

文档另有 `orders/replace/{id}`(更换号)、`orders/resend/{id}`(重发)、`services`/`countries`/`getInventory`(列表)——本次**非目标**，不实现（YAGNI，现有 `SMSProvider` 接口没有这些方法）。

响应示例（取号/取码）：
```json
// getNumber
{"code":0,"message":"","data":{"id":"2046386613387407360","serviceCode":"tg","countryCode":"44","countryPhoneCode":"+44","phoneNumber":"447700900123","creditAmount":3.2,"activationTime":1776316800,"activationEndTime":1776317400}}
// orders/sync/{id}
{"code":0,"message":"","data":{"id":"175847584743","code":"123456","text":"Your verification code is 123456","dateTime":1776316890}}
```

## 3. 改动设计

**只改一个文件**：`services/sms_service/providers/sms_cloud.py`。沿用现有**策略模式**（`SMSProvider` 子类）+ **工厂**（`ProviderRegistry.register("sms_cloud")`），仅重写该适配器内部。

### 3.1 `_get` 助手（核心修正：header 鉴权 + 信封解包 + 错误浮现）

```python
async def _get(self, path: str, params: dict | None = None) -> dict:
    """GET {base_url}{path}，header 带 apiKey；校验信封 code==0，返回 data。"""
    async with httpx.AsyncClient(timeout=30, headers={"apiKey": self._api_key}) as client:
        resp = await client.get(f"{self._base_url}{path}", params=params or {})
        resp.raise_for_status()
        body = resp.json()
    if body.get("code") != 0:
        raise ValueError(f"SMS Cloud {body.get('code')}: {body.get('message')}")
    return body.get("data") or {}
```
关键点：
- 鉴权从 query 改 **header `apiKey`**。
- `code != 0` 一律 `raise ValueError`（含真实 message），**不再把错误静默吞成 0**——上层 service/前端能看到"登录凭证已过期"这类真因。
- 返回 `data`（已解信封），各方法直接取字段。

### 3.2 五个接口方法

```python
async def get_balance(self) -> float:
    data = await self._get("/public/sms/balance")
    return float(data.get("balance", 0))

async def get_number(self, service: str, country: str) -> AcquireResult:
    data = await self._get("/public/sms/getNumber", {
        "serviceCode": service,
        "countryCode": country,   # 文档要 int 编码；上层负责传正确国家编码，provider 透传
    })
    return AcquireResult(
        order_id=str(data["id"]),
        phone_number=data["phoneNumber"],
        provider=self.name,
    )

async def get_code(self, order_id: str, timeout: int = 120) -> CodeResult:
    elapsed, interval = 0, 5
    while elapsed < timeout:
        data = await self._get(f"/public/sms/orders/sync/{order_id}")
        code = data.get("code")
        if code:
            return CodeResult(order_id=order_id, code=code, status=OrderStatus.RECEIVED)
        await asyncio.sleep(interval)
        elapsed += interval
    return CodeResult(order_id=order_id, code=None, status=OrderStatus.TIMEOUT)

async def complete(self, order_id: str) -> None:
    await self._get(f"/public/sms/orders/finish/{order_id}")

async def cancel(self, order_id: str) -> None:
    await self._get(f"/public/sms/orders/cancel/{order_id}")
```

注意：`get_number` 的 `KeyError`（缺 `id`/`phoneNumber`）会自然冒泡为错误；不再像旧代码靠 `"phone" not in result` 手动判（信封已在 `_get` 里判过 `code==0`）。`config_schema`、`_base_url`、`_api_key` property 保持不变。

## 4. 测试方案

**单元测试**（新增 `services/tests/sms_service/test_sms_cloud_provider.py`，mock httpx，离线）：
1. `get_balance` 解析 `data.balance`：mock 返回 `{"code":0,"data":{"balance":8.0}}` → 断言 `== 8.0`。
2. 鉴权头：断言请求带 `apiKey` header（用 httpx MockTransport 或 respx 捕获 request.headers）。
3. 错误信封：mock 返回 `{"code":40001,"message":"登录凭证已过期","data":null}` → 断言 `get_balance()` 抛 `ValueError` 且含 message。
4. `get_number` 字段映射：mock `data.id`/`data.phoneNumber` → 断言 `AcquireResult.order_id/phone_number`，且请求参数为 `serviceCode`/`countryCode`。
5. `get_code` 命中：mock `data.code="123456"` → `CodeResult(code="123456", status=RECEIVED)`；空 code 多轮后超时 → `TIMEOUT`（用小 timeout + monkeypatch `asyncio.sleep`）。
6. `complete`/`cancel` 打对端点 `orders/finish/{id}`、`orders/cancel/{id}`。

**真实 smoke**（`services/scripts/` 下脚本或带 `@pytest.mark.network` 跳过标记）：实打 `/public/sms/balance` 断言 `code==0`、`data.balance` 是 number。默认 CI 跳过（依赖联网 + 真实密钥）。

## 5. 非目标

- 不改 `base.py` 接口、不改 `service.py`、不改其它 provider（hero_sms/sms_bower）。
- 不实现文档里的 replace/resend/services/countries/getInventory。
- 不动前端余额展示（修好后 `data.balance=8.0` 自然正确显示；单位"钻石"标注非本次范围）。
- 不改 DB 已存配置（base_url/apiKey 已正确）。
