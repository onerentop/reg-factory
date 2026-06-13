# Google 注册接码多平台级联配置设计

- 日期：2026-06-13
- 需求：google 注册接码——**前端选接码平台 → 拉该平台国家+价格 → 选国家 → 配价格上限/固定档**，全局存 DB，长期生效。
- 核心变化：google 接码从写死的 `common/sms.py`（firefox→hero-sms）**改走 services sms_service**（sms_cloud/hero_sms/sms_bower 三家，已修好、有余额）。

## 0. 可行性（已实测）

| 平台 | 查价接口 | 实测 |
|---|---|---|
| hero_sms | `getPrices&service=go` | ✅ `{国家ID:{go:{cost,count,physicalCount}}}`，泰国(52) cost 0.1 |
| sms_bower | `getPrices&service=go` | ✅ `{国家ID:{go:{cost,count}}}` |
| sms_cloud | `/public/sms/countries` + `/public/sms/getInventory` | ✅ countries 有国家名；getInventory 含价格/库存（plan 确认字段） |
| google serviceCode | 三家统一 | ✅ `"go"`（sms_cloud `/services` 列表也含 `go`） |

services 取号/取码端点已就绪：`POST /sms/number/acquire {service,country,provider}` → `{order_id,phone_number}`；`GET /sms/number/{order_id}/code` → `{code}`。

## 1. 配置（config_service，key=`gmail_sms_config`，value=JSON）

| 字段 | 含义 | 默认 |
|---|---|---|
| `provider` | 接码平台名 | `"hero_sms"` |
| `country` | 该平台国家 ID | `"52"`（泰国） |
| `max_price` | 价格上限 | `"0.2"` |
| `fixed_price` | 固定价格档开关 | `false` |

## 2. provider 查价能力（services sms_service）

`base.py` 的 `SMSProvider` 加抽象 `async def get_prices(self, service: str) -> list[dict]`，统一返回 `[{"country": "<id>", "country_name": "<可选>", "cost": <float>, "count": <int>}]`：
- **`SmsActivateProvider`**（hero_sms/sms_bower 共用）：`getPrices&service=<svc>` → 展平 `{cid:{svc:{cost,count}}}` 为列表。
- **`SmsCloudProvider`**：`/public/sms/getInventory`（价格/库存）+ `/public/sms/countries`（国家名）合并。plan 确认 getInventory 响应字段。

## 3. sms_service 新路由

`GET /sms/providers/{name}/prices?service=go` → `service.get_prices(name, service)` → 返回该平台 google 的国家+价格+库存列表（按 cost 升序）。gateway `/sms/{path}` 已转发，前端经 `/api/sms/providers/{name}/prices` 访问。

## 4. google 接码接入 services（重构）

`register_gmail_hybrid.py` 的 `browser_phone_and_finalize` 加参数 `sms_config: dict | None`（含 provider/country/max_price/fixed_price）。取号/取码改走 services HTTP（替换 `common/sms.py` 的 `sms.get_phone/get_code`）：
- **取号**：`POST http://localhost:8001/sms/number/acquire {"service":"go","country":<country>,"provider":<provider>}` → `phone_number` + `order_id`。services 内部按 provider 取号；价格上限/固定档由 provider 配置或 acquire 扩展（plan：acquire 是否需透传 max_price/fixed，或在 provider 配置层处理）。
- **取码**：`GET http://localhost:8001/sms/number/{order_id}/code?timeout=<wait>` → `code`。
- **释放/完成**：`POST /sms/number/{order_id}/cancel|complete`。
- 无 sms_config 时 fallback 旧 `common/sms.py`（兼容）。

> 注：max_price/fixed_price 当前 services `get_number(service,country)` 未含价格参数。plan 评估：扩展 `acquire` 透传 maxPrice/fixedPrice 给 provider，还是 provider 取号时读配置。

## 5. 前端：SmsConfigPage「Google 注册接码」块

现有接码平台表格下方加 antd `Card`：
- **平台**下拉（hero_sms/sms_cloud/sms_bower）→ onChange `GET /api/sms/providers/{name}/prices?service=go` → 填充国家下拉。
- **国家**下拉：选项显示「国家名 / cost / 库存」（按 cost 升序，便宜在前）。选中后 `max_price` 默认填该国 cost。
- **价格上限** InputNumber + **固定价格** Switch。
- **保存**：`PUT /api/config/gmail_sms_config` body `{value: JSON.stringify({provider,country,max_price,fixed_price})}`。
- 加载：`GET /api/config/gmail_sms_config` → 回填。

## 6. 链路

```
SmsConfigPage 保存 → gateway /config → config_service(DB)
/register/google 端点 await httpx(trust_env=False) GET config_service /config/gmail_sms_config
  → JSON.parse → 注入 config["sms"] → submit(config, platform="google")
子进程 context["config"]["sms"] → google flow _step_phone_verify
  → browser_phone_and_finalize(..., sms_config=context["config"]["sms"])
  → 走 services 取号/取码
```

## 7. 测试

- **provider get_prices**：mock httpx，hero/sms_bower 展平 getPrices、sms_cloud 合并 inventory+countries。
- **sms_service /prices 路由**：mock service.get_prices，断言 200 + 列表。
- **接码接入**：`browser_phone_and_finalize` 取号/取码走 services（mock services HTTP，断言调 acquire/code）。
- **端点注入**：`/register/google` 读 config_service 注入 `config["sms"]`（mock httpx + task_manager）。
- **前端**：SmsConfigPage Google 块——选平台拉 prices、保存调 PUT（vitest mock fetch）。

## 8. 非目标

- 不改 outlook（不接码）。
- 不做多套 google 接码配置（只一份全局）。
- 不实现各平台全部服务（只 google `go`）。
- 不删 `common/sms.py`（作为 fallback 保留）。
