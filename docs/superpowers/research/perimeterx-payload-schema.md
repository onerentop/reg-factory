# PerimeterX collector 载荷 schema（部分实测，明文字段待解密）

- 日期：2026-06-11
- 来源：`_instrument_perimeterx.py` hook 事件（`_px_events.json`，1438 事件）

## 状态说明

collector 的**最终上报载荷在加密串内**（base64+XOR，见 [crypto-spec](perimeterx-crypto-spec.md)），完整明文字段清单**待 XOR key 还原后**从密文解出。本文记录**已通过 hook 直接观测到的「collector 采集面」**——即它读了哪些指纹/行为信号（这些最终会进加密载荷）。

## 已观测的采集面（hook 直接抓到）

### 1. 静态指纹（`fp_navigator` hook，6 次）
collector 读取的 navigator 字段：
- `navigator.userAgent`
- `navigator.platform`
- `navigator.hardwareConcurrency`
- `navigator.deviceMemory`
- `navigator.languages`

（后续应扩展 hook 覆盖 `screen.*`、WebGL、canvas、`Intl.DateTimeFormat().resolvedOptions().timeZone` 等，当前 `FingerprintHook` 仅覆盖 navigator 核心字段。）

### 2. 行为信号（`behavioral` hook 族）
- `requestAnimationFrame`：捕获 18 次调用 + 时间戳 → collector 监测 rAF 循环节奏（区分真人抖动 vs 机器静止长按，与公开情报一致）。
- 事件监听器注册：捕获 collector 对 `mousedown`/`pointermove`/`pointerdown` 的 `addEventListener`（5 次）→ 确认它在采集指针行为。
- **长按期的 mousedown 频率、坐标方差**：bot 模式无交互未触发；待真人黄金样本捕获 `pointer_stream`（`_recon_perimeterx.py` human 模式已支持录指针流）。

### 3. 出口（`egress` hook）
- 3 次 `XMLHttpRequest.send` 到 `collector-PXzC5j78di.hsprotect.net/api/v2/msft`，body=`payload=<base64>`。

## 待解密确认的明文字段（XOR 还原后填）

PerimeterX 载荷明文通常含（参照公开情报 + 本链路待证）：
- session/challenge token、appId、时间戳、序号（payload#1/#2/#3 递增计数）
- 上述指纹字段的结构化集合
- 行为遥测数组（指针轨迹采样、rAF 时序、mousedown 序列）
- 完整性校验/签名字段

> 待 Phase 2 用还原的 `PayloadDecryptor` 解密语料库样本后，本节替换为**实测字段全清单**，并交 `SchemaDiffer` 做「真人 PASS vs 机器 FAIL」差分 → 得出长按判别字段（Phase 2 伪造靶向）。

## 状态

采集面：**部分实测**（指纹核心字段 + 行为信号已确认）。
明文全 schema：**待 XOR 解密**（依赖 crypto-spec 的 key 提取）。
