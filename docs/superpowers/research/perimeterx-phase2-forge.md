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

## 风险/未知
- session_id/nonce 的获取方式（挑战触发流程需复刻或浏览器辅助一次）。
- IP 绑定：payload 生成 IP 与提交 IP 须一致。
- 行为遥测的"新鲜度"：时间戳/seq 必须与 session 同步，且行为分布需过 ML（黄金真人模板应足够）。
