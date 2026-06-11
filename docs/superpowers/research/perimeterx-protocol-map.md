# PerimeterX 长按协议图（Microsoft signup.live.com 实测）

- 日期：2026-06-11
- 来源：`_recon_perimeterx.py` bot 模式实弹捕获（语料库 `perimeterx_solver/corpus/`，已 gitignore）
- appId：`PXzC5j78di`

## 实测推翻网传文档的关键点

网传文档说 collector 在 `<appId>.px-cdn.net/api/v2/collector`。**MS 实测完全不同**——全走 **hsprotect.net 第一方路由**：

| 角色 | 实测 URL | 方法 |
|---|---|---|
| **collector（载荷上报）** | `https://collector-pxzc5j78di.hsprotect.net/api/v2/msft` | POST |
| collector 脚本（sensor） | `https://client.hsprotect.net/PXzC5j78di/main.min.js` | GET |
| 长按挑战 iframe | `https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di&session_id=<uuid>` | GET |
| 遥测 ns 像素 | `https://stk.hsprotect.net/ns?c=<uuid>`、`https://ift.px-cloud.net/ns?v=<uuid>&j=1` | GET |

- collector 端点路径是 **`/api/v2/msft`**（MS 专属后缀，**不含 "collector" 字样**）→ classifier 必须按 `collector-` 主机名前缀识别（已修，见 `classify.py`）。
- 钉死的 sensor 脚本：`client.hsprotect.net/PXzC5j78di/main.min.js`，sha256 见语料库 `script_refs`（VM 保护、9000+ 行、每刷新换名）。

## 请求时序（bot 仅加载、无交互即触发）

```
GET  signup.live.com/signup
GET  iframe.hsprotect.net/index.html?app_id=PXzC5j78di&session_id=...
GET  client.hsprotect.net/PXzC5j78di/main.min.js   (sensor)
POST collector-pxzc5j78di.hsprotect.net/api/v2/msft   payload#1   (200)
POST collector-pxzc5j78di.hsprotect.net/api/v2/msft   payload#2   (200)
POST collector-pxzc5j78di.hsprotect.net/api/v2/msft   payload#3   (200)
GET  stk.hsprotect.net/ns?c=...
GET  ift.px-cloud.net/ns?v=...&j=1
```

- 一次加载即自动发 **3–4 次 collector POST**（无需任何交互）。长按过码后应有额外的带行为数据的 collector POST（待真人黄金样本确认）。

## 载荷形态

- collector POST body：`payload=<base64>`（form 编码，单字段）。
- **所有 payload 共享固定前缀 `aUkQRhAIEH`**（base64 层）→ 解码后固定字节头（见 crypto-spec）。
- 明文字段（网传的 appId/tag/uuid/ft/pxhd）在 MS 这条链路上**未见于 body 外层**，疑似全在加密串内。待解密确认（见 payload-schema）。

## Cookie 链

| 节点 | PX cookie |
|---|---|
| on_load | （空，挑战未起时） |
| after_attempt | `pxcts`、`_pxvid`、`_px3`、`_pxde` |

- **关键坑**：`_px3` **仅加载就常驻**（没长按也有）→ 不能用「`_px3` 存在」判过码。`_px3` 是携带分值的 token，靠**值/分值**区分 pass/fail，不是有无。真人黄金样本的 pass 判定改为**真人显式确认**（`_recon_perimeterx.py` human 模式）。

## 状态

Phase 0 侦查：**完成**（bot FAIL 样本 ≥2、协议图实测、脚本钉死）。
待补：真人 PASS 黄金样本（需真人手动长按，命脉用于 Phase 1 差分）。
