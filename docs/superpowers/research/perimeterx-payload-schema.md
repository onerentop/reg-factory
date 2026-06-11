# PerimeterX collector 载荷 schema —— ✅ 已解密

- 日期：2026-06-11
- 来源：原始CDP调试器 dump（`_px_pause_dump.json`）+ `Px2Decryptor` 解密

## ✅ 解密后真实结构

`payload = base64(XOR(JSON, 0x32))`（见 [crypto-spec](perimeterx-crypto-spec.md)）。解出的明文是 JSON：

```
[
  {
    "t": "<混淆类型id, base64>",           // 例 "GCQiLl1BJhk="
    "d": {                                 // data 字典
      "<混淆字段名base64>": <值>,           // 字段名经 base64 混淆(VM字符串表)
      "SlpwEAw5eSc=": "https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di&session_id=<uuid>",
      "VQEvCxBmIj4=": 1,
      "dWFPKzAARxE=": "Win32",             // navigator.platform
      "<...>": <二进制指纹哈希>,            // canvas/audio/webgl，嵌入的高位字节
      "<...>": "b08a1160-6555-...",        // 某 UUID
      ...
    }
  },
  ... // 多个采集事件对象
]
```

- 字段名是 **base64 混淆**（解开后还需对照 VM 字符串表/二次解码才得可读名——下一步）。
- 值类型：URL、字符串(平台/语言等)、数字、UUID、**原始二进制指纹哈希**（故明文非严格 JSON）。
- query-string 形态的外层字段（`appId=/tag=/uuid=/seq=/pxhd=/jsc=/rsc=`）是 **body 层**（payload 之外的 form 字段），调试器闭包常量已暴露。

## 待细化
- 解开各混淆字段名（base64 → 可能再 XOR/查表）得到可读语义名。
- 真人 PASS 黄金样本解密后，`SchemaDiffer` 对比真人 vs 机器，定位长按判别字段（Phase 2 靶向）。

---

## （历史）hook 观测到的采集面

以下为 Phase 1 中途 hook 直接观测（仍有效，与解密结果互证）：

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
