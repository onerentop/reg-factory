# Google 注册接码配置（前端可配，全局存 DB）设计

- 日期：2026-06-13
- 需求：google 注册接码的**国家 + 价格**前端可配置（全局，存 DB，长期生效）
- 背景：当前参数硬编码在 `.env`（`SMS_HERO_COUNTRIES=52`、`SMS_MAXPRICE_GMAIL=5`、`SMS_HERO_FIXED_PRICE` 默认 true），子进程经 `os.environ` 读，前端改不了。实测泰国(52) google 号真实价 **0.1**、12139 个号，但 `maxPrice=5 + fixedPrice=true` 强制买 5 的价档（不存在）→ NO_BALANCE。

## 1. 配置字段（config_service，key=`gmail_sms_config`，value=JSON 字符串）

| 字段 | 含义 | 默认 |
|---|---|---|
| `country` | hero-sms 国家 ID | `"52"`（泰国） |
| `max_price` | 价格上限（买 ≤ 它的号） | `"0.2"`（覆盖 0.1 号 + 余量） |
| `fixed_price` | 固定价格档开关 | `false`（买 ≤ 上限最便宜，鲁棒） |

value 存为 JSON 字符串：`{"country":"52","max_price":"0.2","fixed_price":false}`。

## 2. 前端：SmsConfigPage 加「Google 注册接码」块

在 `frontend/src/pages/SmsConfigPage.tsx` 现有接码平台表格下方加一个 antd `Card`「Google 注册接码」：
- 字段：`country`（InputNumber）、`max_price`（InputNumber step 0.1）、`fixed_price`（Switch）。
- 加载：`GET /api/config/gmail_sms_config` → 取 `data.value` → `JSON.parse` → 填表单；不存在时用默认值。
- 保存：`PUT /api/config/gmail_sms_config`，body `{ value: JSON.stringify({country, max_price, fixed_price}) }`，成功 `message.success`。
- 经 gateway `/config/{key}` 转发到 config_service（已有转发）。

## 3. 传递链路（DB 配置 → 注册子进程接码）

```
SmsConfigPage 保存 → gateway /config → config_service(DB)
注册触发 /register/google:
  端点 await httpx GET config_service /config/gmail_sms_config
    → JSON.parse → 注入 config["sms"] = {country, max_price, fixed_price}
    → task_manager.submit(config=config, platform="google")
  子进程 context["config"]["sms"]
    → google flow _step_phone_verify
    → browser_phone_and_finalize(page, profile, ctx, profile_id, sms_config=context["config"].get("sms"))
    → 优先用 sms_config(country/max_price/fixed_price)，fallback os.environ(兼容旧 .env)
```

**端点读 config_service**：`/register/google` 是 gateway async 端点，用 `await _httpx.AsyncClient(trust_env=False).get(f"{_CONFIG_URL}/config/gmail_sms_config")` 读（await 不阻塞事件循环、config_service 是独立进程 8003，不触发之前的自调用死锁）。读不到/异常时用默认值。

## 4. browser_phone_and_finalize 改造（优先配置，fallback env）

`register_gmail_hybrid.py:258` `browser_phone_and_finalize(page, profile, ctx=None, profile_id=None)` 加参数 `sms_config: dict | None = None`：
```python
sms_config = sms_config or {}
hero_country = str(sms_config.get("country") or os.environ.get("SMS_HERO_COUNTRIES", "52").split(",")[0]).strip()
max_price = str(sms_config.get("max_price") or os.environ.get("SMS_MAXPRICE_GMAIL", "0.2"))
fixed = sms_config["fixed_price"] if "fixed_price" in sms_config \
        else os.environ.get("SMS_HERO_FIXED_PRICE", "false").lower() in ("1", "true", "yes")
```
其余（hero_svc/max_tries/code_wait）保持 os.environ 默认（非本次配置范围）。

## 5. 顺带修当前 bug

- `.env` 默认 `SMS_MAXPRICE_GMAIL=5` → 改 `0.2`，并加 `SMS_HERO_FIXED_PRICE=false`（作为无 DB 配置时的兜底默认）。
- 这样即使 DB 没配，也能买到 0.1 的泰国号。

## 6. 测试

- **前端**：SmsConfigPage 的 Google 接码块渲染 + 保存调 `PUT /config/gmail_sms_config`（vitest mock fetch）。
- **后端**：`/register/google` 端点读 config_service 注入 `config["sms"]` → submit 收到（mock httpx + task_manager，断言 submit 的 config["sms"]）。
- **接码改造**：`browser_phone_and_finalize` 的配置优先级——浏览器自动化难单测，靠 `sms_config` 解析逻辑可抽小函数单测（country/max_price/fixed 的 config-优先-env-兜底）。

## 7. 非目标

- 不接入 services sms_service（保持 common/sms.py 的 hero-sms 链路）。
- 不配 service code(`go`)/max_tries/code_wait/country_blacklist（保持现状）。
- 不动 outlook（不接码）。
- 不做多套接码配置（只一份全局 gmail_sms_config）。
