# PerimeterX Phase 2 伪造 —— 提交链路实测 + 伪造路线

- 日期：2026-06-11
- 工具：`_px_submit_probe.py`、`Px2Encoder`（`perimeterx_solver/analysis/decryptor.py`）

## ✅ 已打通的提交链路（实测）

**端点**：`POST https://collector-PXzC5j78di.hsprotect.net/api/v2/msft`
**body**（form 形态，字段实测）：`payload=<base64> & appId & tag & uuid & ft & seq & en & cs & pc & sid`
**headers**：`Content-Type: application/x-www-form-urlencoded`、`Origin/Referer: https://iframe.hsprotect.net`、UA。

**响应**（实测重放黄金长按 body，status 200）：
```json
{"do": null, "ob": "<base64>"}
```
- `ob` **同样 XOR 0x32 + base64 编码**，解出管道分隔串：
  ```
  ...|_pxde|330|<sig>:<base64>|true|300
                       └ base64 = {"timestamp":...,"f_kb":0}
  ```
- `do`：拦截/动作决策（null = 不拦截）。`ob`：要 set 的 cookie 串（collector 脚本解析后 set document.cookie）。

## 关键结论

- **collector 接受伪造 payload 并正常响应**（不因"非浏览器直发"而拒）。
- 重放**过期黄金**：拿到 `_pxde`（富化）但**无 `_px3`（清关）**、未被 block → **清关 cookie `_px3` 需要"新鲜+有效 session"的 payload**（session_id/时间戳/seq 等必须当下有效，疑还绑 IP）。
- 编码/解码双向已掌握（`Px2Encoder`/`Px2Decryptor`，往返测试过）。

## 伪造路线（下一步）

1. **识别 session 绑定字段**：解密黄金长按 JSON，按值形态定位 `session_id`(UUID)、时间戳(13位)、`seq`、nonce/挑战令牌——哪些必须刷新。
2. **新鲜 session 建立（纯HTTP）**：复刻初始 collector 握手拿 `_pxhd`/`_pxvid` + 触发挑战拿 `session_id`（来自 `iframe.hsprotect.net/index.html?...&session_id=`）。
3. **PayloadBuilder**：组装长按遥测 JSON = 黄金真人行为模板（pointerdown→up 坐标/时长 11.7s/movement）+ 刷新的 session 字段 + 当前时间戳。
4. **Px2Encoder → 提交 → 验 `_px3`**：解响应 `ob`，看是否含 `_px3` 清关 cookie。迭代到拿到清关。
5. 拿到 `_px3` → 注入 requests 会话 → 协议侧 CreateAccount（Arkose HSol 走现有 solver）→ 全 HTTP 注册。

## 实测进展（2026-06-11 续，`_px_forge.py` / `_px_submit_probe.py`）

**session 字段映射（①完成）**：body 表单字段 = `appId/tag/uuid/ft/seq/en/cs/pc/sid/p1/vid/ci/cts/rsc`。
- 固定常量：`appId`、`ft=369`、`en=NTA`、`tag=YjIYfyxJHRR9`（**跨会话稳定**，脚本版本常量）。
- **客户端自铸**：`uuid/vid/p1/cts/sid/ci` 全是含时间戳的 UUIDv1；`sid` = UUID + **隐形 Unicode tag 字符编码的时间戳**。
- 递增：`seq`/`rsc`。每请求变：`pc`(16位nonce)。每会话固定签名：`cs`(64hex)。
- **session 不是服务端下发，是客户端自铸**（②大发现）→ 纯HTTP伪造高度可行。

**cs（会话签名）**：custom sha256（`crypto.subtle` 调用=0），简单字段拼接/HMAC 暴破未中（含脚本内隐藏 salt）。**绕开策略**：hybrid-mint——浏览器加载时合法算出 cs，HTTP 侧直接复用。

**响应协议**：`POST .../api/v2/msft` → `{"do":<决策>,"ob":<XOR0x32+base64>}`。`ob` 解出管道串：
- `IoooII|_px3|330|<value>` = set `_px3` cookie（**seq=1 初始响应就设 _px3 低分 token**，过码是升级其分值）。
- `IIoIIo|<sid>~~~~|cu~~~~|<num>` = 设 session 值。重放过期黄金 → `do:null` + `_pxde`。

**长按 payload 结构（关键）**：解密后**不含任何 session UUID**（只有行为遥测 + 2 个时间戳）→ session 绑定全在 body 字段。行为遥测核心：`["BODY","#px-captcha",""]` + `pointerdown/up` 坐标(582,718.67) + 时长11684ms + movement + de-DE。

**hybrid-mint 伪造实测**：浏览器到挑战拿 fresh session 字段(cs/sid/...) → HTTP 提交「黄金行为+刷新时间戳」长按 payload → **被接受(200)但 `do:[]` 空、无 _px3 升级**。

## ⚠️ 剩余硬核（真正的最后一里）

编码/session/提交/响应协议**全部已解**。唯一未破：**为活体挑战生成能过 ML 的行为遥测**。
- 黄金坐标(582,718.67)是**那次挑战按钮位置**；时序/rAF/微动绑定当次挑战 → 逐字重放对新挑战不匹配。
- 要过：读活体挑战参数（按钮几何/nonce/起始时刻）→ 生成既像真人、又匹配当前挑战的行为遥测（黄金给"真人形状"，需适配到活体坐标/时序）→ 过 PerimeterX 行为 ML。
- 这是 PerimeterX 之所以难、$1500 悬赏的核心。下一步：①读活体 #px-captcha 几何调整黄金坐标；②对齐挑战起始时序/rAF；③逆 pc nonce；④迭代到 _px3 升级。

## 风险/未知
- session_id/nonce 的获取方式（挑战触发流程需复刻或浏览器辅助一次）。
- IP 绑定：payload 生成 IP 与提交 IP 须一致。
- 行为遥测的"新鲜度"：时间戳/seq 必须与 session 同步，且行为分布需过 ML（黄金真人模板应足够）。
