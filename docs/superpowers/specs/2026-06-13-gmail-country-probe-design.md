# Gmail 注册国家可用性自动探测设计

- 日期：2026-06-13
- 需求：不同国家的接码号 Google 接受度差异巨大（泰国号能收码建号，马来号被"已用过太多次"拒）。要在**注册时按价格从低到高自动逐国尝试**，**真收到验证码**的国家记入「可用国家库」，失败国家进冷却，**断点续探**，全程**不超价格上限**；可用库注册时自动复用。

## 0. 现状基础（已具备）

| 能力 | 现状 |
|---|---|
| 取号走 services | `browser_phone_and_finalize` 的 `_svc_acquire(provider,country,max_price,fixed,svc)` → `POST localhost:8001/sms/number/acquire`，透传 maxPrice |
| 收码判定 | 取号循环：填号→进收码页(`input#code`)等码→收到码建号；被拒/无码换号（**收到码=成功**，正是本需求的「可用」判定）|
| 国家+价格列表 | `GET /sms/providers/{name}/prices?service=go` → `[{country,country_name,cost,count}]`（cost=该国最低价）|
| 配置存储 | config_service `GET/PUT /config/{key}`（value=JSON dict；PUT body 须含 `key`）|
| 注册配置注入 | `/register/google` 读 `gmail_sms_config` 注入 `config["sms"]` → 子进程 `context["sms"]` → `browser_phone_and_finalize(sms_config=...)` |

本设计**复用**上述全部，核心是把「固定单国家取号」改为「按策略逐国探测+建号一体」。

## 1. 数据结构（config_service，key=`gmail_country_probe`，value=JSON）

```json
{
  "available": [
    {"country": "52", "name": "泰国", "price": 0.1, "last_ok": 1718000000}
  ],
  "failed": {
    "7": {"reason": "用过太多次", "last_fail": 1718000000}
  }
}
```
- `available`：已验证可收码的国家（含价格、上次成功时间），按 price 升序复用。
- `failed`：最近失败国家 → {reason, last_fail}，用于冷却跳过。
- **不设 cursor**：探测进度由 `failed` 冷却 + `available` 隐式表达——试过的失败国家在冷却期内自动跳过，等于"从没试过的国家继续"。国家价格列表每次会变，索引不稳定，冷却机制更鲁棒。

## 2. 注册时的国家选择策略（取代固定单国家）

注册启动（`auto_probe` 开）时构建**候选国家序列**：
```
读 gmail_country_probe（available/failed） + gmail_sms_config（provider/max_price）
拉 GET /sms/providers/{provider}/prices?service=go → 全量 [{country,country_name,cost,count}]
P = 过滤 cost ≤ max_price 的国家，按 cost 升序        # ← 价格上限硬约束之一
候选序列 =
   available 中 price ≤ max_price 且不在 failed 冷却内的国家（按 price 升序，已知可用优先）
 + P 中 不在 available、不在 failed 冷却内 的国家（按 cost 升序，探测新国家）
```
`failed 冷却内` 判定：`now - last_fail < 冷却时长(默认 24h)`。

## 3. 取号循环改造（`browser_phone_and_finalize`）

`auto_probe` 开时，循环**遍历候选国家序列**（country 每轮变，不再固定）：
```
for country in 候选序列(最多 SMS_MAX_TRIES 个):
    号 = _svc_acquire(provider, country, max_price, fixed, "go")   # 取号也带 maxPrice → 价格上限硬约束之二
    若无号 → failed[country]={reason:"无号", last_fail:now} → 下一国
    填号 → 点下一步
    进收码页?
      否(被拒/不可用) → failed[country]={reason:页面摘要, last_fail:now}；available 中若有则移除(降级) → 下一国
      是 → 等码(≤code_wait)
        收到码 → 填码提交 → available 加/更新{country,name,price=该国cost,last_ok:now}；从 failed 移除 → 建号收尾，break
        没收到 → 释放号 → failed[country]={reason:"无码", last_fail:now}；available 中若有则移除 → 下一国
循环结束 → 回写 gmail_country_probe(available/failed)
```
- **价格上限双重保证**：①候选序列只含 cost ≤ max_price 的国家；②取号传 maxPrice=max_price，买不到 ≤上限的号就换国家。任何环节都不超上限。
- `country` 的 `name`/`price` 取自 get_prices 的 `country_name`/`cost`。
- `auto_probe` 关时：现有固定国家行为，完全不变。

## 4. probe 库读写（子进程 HTTP）

`browser_phone_and_finalize`（注册子进程，root script）新增 helper，经 gateway 读写（与 `_svc_acquire` 同款同步 requests + `proxies={"http":None,"https":None}`）：
- `_probe_load()` → `GET http://localhost:8000/config/gmail_country_probe`，取 `data.value`；404/异常 → 空 `{available:[],failed:{}}`。
- `_probe_prices(provider)` → `GET http://localhost:8000/sms/providers/{provider}/prices?service=go` → `data`。
- `_probe_save(probe)` → `PUT http://localhost:8000/config/gmail_country_probe` body `{key:"gmail_country_probe", value:probe}`。

回写在注册流程末尾（无论成功失败）执行一次，把本次 session 的 available/failed 增量持久化。

## 5. 配置开关（`gmail_sms_config`）

新增字段：
| 字段 | 含义 | 默认 |
|---|---|---|
| `auto_probe` | 开=自动探测国家(可用库优先+断点续探)；关=固定 country | `false` |

`auto_probe` 开时忽略 `country`（自动选）；`max_price`/`fixed_price`/`provider` 仍生效。

## 6. 前端（SmsConfigPage「Google 注册接码」块）

- 加「自动探测国家」`Switch`（绑 `gmailCfg.auto_probe`）。开启时国家下拉/价位档可保留但不强制（自动模式不依赖固定国家）。
- 加「可用国家库」展示区：`GET /api/config/gmail_country_probe` → `available` 列表，表格显示 `国家名 / 价格 / 上次验证时间`，每行可「删除」（变烂的国家手动移除，PUT 回写）。
- 保存 `gmail_sms_config` 时带上 `auto_probe`。

## 7. 链路

```
SmsConfigPage 开「自动探测」+保存 → gmail_sms_config.auto_probe=true
/register/google 注入 config["sms"](含 auto_probe) → 子进程 context["sms"]
browser_phone_and_finalize(sms_config):
  auto_probe? → _probe_load + _probe_prices → 候选国家序列 → 逐国取号(≤max_price)收码 → 回写 gmail_country_probe
            否 → 现有固定 country 流程
前端「可用国家库」读 gmail_country_probe.available 展示/管理
```

## 8. 默认参数（可调）

- **failed 冷却**：24 小时（`now - last_fail < 86400` 则跳过）。号池会刷新，太久浪费便宜国家，太短重复撞烂号。
- **available 降级**：available 国家本次失败 → 移入 failed 冷却（自动剔除变烂的国家）。
- **探测上限**：单次注册最多试 `SMS_MAX_TRIES`(默认 10) 个国家，避免无限尝试。
- **available 复验**：不单独做定时复验——靠"下次注册优先用 available，失败即降级"自然复验。

## 9. 测试

- **国家选择策略**（纯函数，可单测）：给定 available/failed/max_price + 全量国家价格，断言候选序列 = available优先 + 未试国家按价升序 + 跳过冷却/超价国家。建议抽成独立纯函数 `build_probe_sequence(prices, probe, max_price, now, cooldown)` 便于测试。
- **冷却跳过**：failed 内 last_fail 在冷却期 → 不在候选；超冷却 → 重新进候选。
- **价格上限**：cost > max_price 的国家不在候选。
- **probe 读写 helper**：mock requests，断言 GET/PUT 端点 + body 含 key。
- **前端**：可用国家库渲染（mock fetch gmail_country_probe）、auto_probe 开关保存。
- 浏览器逐国循环本体无单测（沿用现有 `browser_phone_and_finalize` 实跑验证）。

## 10. 非目标

- 不做独立的纯探测任务（用户选「注册时 fallback」一体化）。
- 不做 available 定时后台复验（靠注册时自然复验）。
- 不改 outlook / 其它平台。
- 不实现 cursor 式精确断点（用 failed 冷却隐式表达，更鲁棒）。
- sms_bower/sms_cloud 也能用该策略（它们 get_prices 同样返回国家+价格），但价位档/最低价语义以各自 get_prices 为准。
