# PerimeterX 长按验证码逆向求解器 — 设计

- 日期：2026-06-11
- 分支：feat/ixbrowser-migration
- 状态：设计已确认，待落实施计划
- 关联记忆：[[outlook-perimeterx-solvers]]、[[outlook-hybrid-solution]]、[[feedback-design-patterns]]

## 1. 背景与问题

Outlook（signup.live.com）注册流水线有两道验证码，串联如下：

```
[① PerimeterX 长按  hsprotect.net (app_id=PXzC5j78di)]   ← 唯一未解的墙
      ↓ 过了才到
[填表] → [② Arkose FunCaptcha → HSol token]              ← 已有 reversed solver（_funcaptcha_solver/）
      ↓
CreateAccount
```

第②道（Arkose）已由现成的 `_funcaptcha_solver`（纯 HTTP、reversed BDA、preset=outlook_register）解决。**唯一瓶颈是第①道 PerimeterX 长按。**

### 已排除的非根因（2026-06-11 实测 9/9 失败后定性）

浏览器隐身做到 rebrowser-bot-detector **全绿**（runtimeEnableLeak / navigatorWebdriver / viewport / pwInitScripts / bypassCsp 全 🟢），指纹×IP 地理完美对齐，长按机制/时长/坐标正确（截图证实 "Please try again" 是评分判负、非坐标错），跨两家代理商两个区域（1024proxy DE、IPRoyal JP/DE 真住宅 ISP）依然 **0/9**。

**结论**：瓶颈不是浏览器自动化检测（已彻底洗白），也不止某个脏 IP 池。鼠标模拟长按这条路已到顶——PerimeterX 长按在低信誉会话上按设计就是软封。要确定性通过，只能走「逆向 collector → 伪造行为载荷 → 拿通过 cookie」，即对 PerimeterX 做和 Arkose solver 同款的协议级破解。

## 2. 目标与范围

### 目标终态

一个**本地 HTTP 求解服务**（与 `_funcaptcha_solver` 同构，纯协议、无浏览器）：

```
POST /perimeterx/solve
  in : {app_id, page_url, proxy, ...}
  out: {_px3, _pxhd, _pxvid, vid, ...}   # 清关 cookie 链
```

注册流水线在长按处把「浏览器长按」整段替换为「调本地 PX 服务拿 cookie 注入」，Arkose HSol 仍走现有 solver → **全 HTTP 注册闭环**。

### 本 spec 范围

- **详写**：Phase 0（侦查 & 协议图）+ Phase 1（反混淆 & 载荷 schema）——这是让后续破解可做的地基。
- **里程碑列出（不详写）**：Phase 2（伪造 & 校验，核心难关）+ Phase 3（产品化 & 接入）。

### 非目标

- 不在本 spec 内完成 Phase 2 的完整 crypto 破解（不确定性最高，单列里程碑、带 go/no-go 门）。
- 不追 VM 轮换：分析全程针对 Phase 0 钉死的某一份脚本版本。
- 不改动 Arkose 求解链路（已可用）。

## 3. 目标架构

```
                   ┌─────────────────────────────────────────┐
   注册流水线  ───▶ │  PxSolverService (Facade, 本地 HTTP)       │
   (Outlook)       │   solve(ctx, proxy) → 清关 cookie 链        │
                   └─────────────────────────────────────────┘
                              │  内部（逆向产物）
        ┌─────────────────────┼─────────────────────────┐
        ▼                     ▼                          ▼
  ChallengeContext      PayloadBuilder              Signer (Strategy)
  (挑战参数/cookie/脚本) (Builder, 分步装配载荷)     (签名/加密, 换版可替换)
                              ▲
                       BehavioralSource (Strategy)
                       (合成合法行为数据 / 重放真人特征)
```

落点：新建顶层包 **`perimeterx_solver/`**（与 `_funcaptcha_solver/` 平级），独立可测、低耦合。

### 设计模式（落实到类/接口）

- **Facade** `PxSolverService`：对外只暴露 `solve()`，藏住全部逆向细节。
- **Strategy** `Signer`（签名/加密算法，PX 换版可替换）、`BehavioralSource`（合成 vs 真人重放，行为数据源可插拔）。
- **Builder** `PayloadBuilder`：分步装配传感器载荷。
- **Repository** `SampleCorpus`：统一存取「真人 PASS / 机器 FAIL」配对样本。
- **Template Method** `ReconHarness`：recon→hook→diff 的固定骨架，各 Phase 填空。
- **Memento** `PxCookieSnapshotter`：在生命周期各节点快照 cookie 状态。

## 4. 逆向方法论

**路线 1（动态插桩优先）为主干 + 对签名段做定点静态反混淆 + 用真人样本做差分校验。** 这是现代反 antibot 逆向标准打法。

- 不强啃静态 VM（PerimeterX 是 VM 保护 + 9000+ 行、函数/变量名每刷新都变、字符串 Base64+XOR）。
- 把 collector 跑在受控环境，按**稳定行为锚点** hook（出口/编码/加密/行为采集），观察 ground truth，重建载荷生成逻辑。
- 只对加密/签名那一小段做静态还原。
- 用真人 PASS 黄金样本差分校验，火力集中在「真正被校验的字段」。

整个工程**分 4 阶段、每段独立产出、带 go/no-go 门**：

| Phase | 产出物 | 谁主力 | Gate |
|---|---|---|---|
| 0 侦查 | 协议图 + 配对样本语料库 + 抓取工具 | 我 | 拿到真人 PASS 完整载荷+响应？ |
| 1 反混淆 | 载荷 schema + 定位签名段 + 解密器 + 差分报告 | 我搭台、定位 | 签名算法可还原？ |
| 2 伪造 | Python 载荷生成器 + 差分校验台，打到「接受」 | 团队逆向 + 我校验台 | 真能拿到通过 cookie？ |
| 3 产品化 | `perimeterx_solver/` 服务 + 接入注册流水线 | 我 | E2E 出号？ |

## 5. Phase 0 详细设计：侦查 & 协议图

**目标**：把网传协议变成本条 Microsoft 链路上的实测 ground truth，产出配对样本语料库（Phase 1/2 的依据）。

### 已知协议骨架（待实测确认）

```
加载 collector 脚本 (client.px-cloud.net/PXzC5j78di/main.min.js)
      ▼
首屏 collector POST  ──▶ PXzC5j78di.px-cdn.net/api/v2/collector   (payload#1, 加密+Base64 + 明文 appId/tag/uuid/ft/pxhd)
      ▼  返回 _pxhd / 触发挑战
hsprotect.net iframe (app_id=PXzC5j78di) 长按挑战渲染
      ▼  长按期采集 mousedown 频率 / 坐标方差 / requestAnimationFrame
长按 collector POST#2 ─▶ .../api/v2/collector   (payload#2)
      ▼  成功
返回 _px3 清关 cookie + X-PX-Authorization；cookie 链 _px3/_pxhd/_pxvid/pxcts
```

### 要抓的 5 类数据（一次完整长按生命周期）

1. 全部 PX 域网络流量（`*.px-cdn.net`/`*.px-cloud.net`/`hsprotect.net`）：每个 req/resp 的 body+headers+时序，尤其两次 collector POST 及返回 `_px3` 的那次。
2. collector / 挑战 JS 原文 + hash + 版本（应对轮换）。
3. cookie 在各节点的快照（`_px3/_pxhd/_pxvid/pxcts/_pxff*`）。
4. 真人 PASS 会话的**指针事件流**（带高精度时序）——行为 ground truth。
5. 配对样本：机器 FAIL + 真人 PASS，同一 harness，供差分。

### 组件

| 组件 | 模式 | 职责 |
|---|---|---|
| `PxTrafficRecorder` | — | CDP 网络抓取，过滤 PX 域，落 req/resp body+headers+时序 |
| `PxScriptDumper` | — | 抓 collector/挑战 JS 原文 + hash + 版本 |
| `PxCookieSnapshotter` | Memento | 各生命周期节点快照 PX cookie |
| `HumanPassCapture` | — | 真人手动长按模式：住宅 IP 手动过一次，全程录网络+指针流 → 黄金样本；容忍多次失败，只在成功那次落黄金档 |
| `SampleCorpus` | Repository | 配对存样本（JSON+原始 body），按 run_id/结果索引 |
| `ReconHarness` | Template Method | 固定骨架：起会话→挂录制→跑到挑战→收尾存档，bot/human 两种填充 |

### 产出物

- 协议图文档 `docs/superpowers/research/perimeterx-protocol-map.md`：实测端点、请求时序、payload 字段清单（明文/密文区分）、cookie 链、脚本版本+hash。
- 配对样本语料库 `perimeterx_solver/corpus/`：≥1 真人 PASS（黄金）+ N 机器 FAIL。

### 关键依赖与风险

- **真人黄金样本是命脉**：差分全靠它。真人住宅 IP 长按 ~20% 成功率 → 可能手动试几次才录到一个 PASS。已与用户确认其真机/住宅环境可手动过。
- **VM 轮换**：`PxScriptDumper` 钉死某次会话的精确脚本版本+hash，Phase 1 全程针对该版本，不追轮换。

## 6. Phase 1 详细设计：反混淆 & 载荷 schema

**目标**：基于 Phase 0 钉死的 collector，搞清「明文载荷 schema」+「加密/签名算法」，并能解密 Phase 0 语料库 → 差分出真人 vs 机器的判别字段。

### 方法：按稳定行为锚点 hook（不按名字，名字每刷新都变）

| 锚点（稳定边界） | hook 它能拿到 |
|---|---|
| `XMLHttpRequest.send`/`fetch`/`sendBeacon` → `*/api/v2/collector` | 最终加密串（出口），反向溯源 |
| `btoa`/`atob`/`JSON.stringify`/`TextEncoder` | 加密前的明文传感器对象 → schema |
| `crypto.subtle` / 自定义 XOR 循环 | 加密/签名算法本体 + 密钥来源 |
| `addEventListener(mousedown/pointermove)`、`requestAnimationFrame`、`performance.now` | 长按期行为采集点 |
| `navigator/screen/window` 属性读取（Proxy 陷阱） | 指纹采集面清单 |

### 组件

| 组件 | 模式 | 职责 |
|---|---|---|
| `PxInstrumentedSession` | Facade | 在受控浏览器跑钉死的 collector，统一暴露捕获产物 |
| `HookInjector` | Strategy（NetworkEgress/Encoding/Behavioral/Fingerprint 各族） | 注入行为锚点 hook，可单独增删 |
| `PayloadTracer` | — | 串「明文对象 → 加密调用 → 最终串」，重建装配管线 |
| `CryptoLocator` | — | 从 trace 定位加密/签名函数 + 密钥派生，抠出那段做定点静态还原 |
| `PayloadDecryptor` | Strategy | 算法摸清后解密语料库样本（实现可插拔） |
| `SchemaDiffer` | — | diff 机器 FAIL vs 真人 PASS 明文，排序判别字段 |

### 关键 payoff：解密 → 差分

Phase 0 抓到的真人 PASS 是密文。Phase 1 还原解密算法后，把真人 PASS 与机器 FAIL 都解成明文，`SchemaDiffer` 直接给出「PerimeterX 在长按里看哪几个字段、真人和我们差在哪」——Phase 2 的靶向清单，把盲打变靶向。

### 产出物

- 载荷 schema 文档（字段清单 + 标注行为字段）
- crypto 规格（算法 / 密钥派生 / IV-nonce）
- 可用的 `PayloadDecryptor`（代码）
- 差分报告（真人 vs 机器判别字段）

### Gate 与风险

- **Gate**：签名/加密能否干净抠出并重实现？
- **反插桩**：VM 可能检测被 hook 的原生函数（`toString` 非原生码）。对策：出口优先用 CDP Network 层截、JS hook 保留原生 `toString` 伪装、在正确边界用 Proxy。
- **密钥由 VM 现算、静态不可复刻**：兜底——把活体 VM 当**签名 oracle**（喂明文取密文），作为 Phase 2 分支策略（solver 内部跑隔离 JS 运行时，对注册流水线仍无浏览器）。

## 7. Phase 2 里程碑（单列，门后目标）

伪造 & 校验——核心难关。基于 Phase 1 的 schema + crypto + 差分清单：

- `PayloadBuilder` 重实现明文载荷装配（Python）。
- `BehavioralSource`（Strategy）产出合法行为数据：合成「类真人」信号（mousedown 频率/坐标方差/rAF 时序按真人分布生成），或重放 Phase 0 真人指针特征。
- `Signer`（Strategy）：静态重实现 或 VM-oracle 兜底。
- 差分校验台：POST 到 collector 端点 → 检查是否「接受」+ 拿 `_px3` → 对照真人语料库迭代收敛到接受。
- **Gate**：真能稳定拿到通过 cookie？通过率指标达标才进 Phase 3。

## 8. Phase 3 里程碑（单列）

产品化 & 接入：

- 包成本地 HTTP 服务 `PxSolverService`（createTask/getTask 或同步 solve，与 `_funcaptcha_solver` 对齐）。
- `register_outlook_standalone` 长按段替换为「调 PX 服务拿 cookie 注入 context」，Arkose HSol 仍走现有 solver。
- 失败安全：solver 不可用/超时 → 回退现浏览器长按（FallbackPolicy 语义），系统照常运转。
- **Gate**：E2E 全 HTTP 出号。

## 9. 错误处理与风险汇总

| 风险 | 阶段 | 对策 |
|---|---|---|
| 真人黄金样本难录（~20%） | 0 | `HumanPassCapture` 容忍多次失败、只落成功档；可多轮采集 |
| VM 脚本轮换 | 0–1 | 钉死版本+hash 分析；换版重跑 harness（可复用） |
| 反插桩检测 hook | 1 | CDP Network 层截出口；hook 保留原生 toString；Proxy 边界 |
| 加密密钥 VM 现算不可静态复刻 | 1–2 | VM-oracle 兜底（隔离 JS 运行时当签名机） |
| _px3 与 IP/指纹绑定 | 2–3 | solve 时传入与注册同一代理；cookie 注入同会话 |
| PX 升级使破解失效 | 全 | 分层设计（Signer/BehavioralSource 可替换）；harness 可复跑重逆 |

## 10. 测试策略与成功度量

- **Phase 0**：harness 能在一次会话内完整捕获 5 类数据并存档；至少录到 1 个真人 PASS 黄金样本。验收 = 协议图文档字段齐全 + 语料库 ≥1 PASS。
- **Phase 1**：`PayloadDecryptor` 能解密语料库样本为可读明文；`SchemaDiffer` 输出非空判别字段列表。验收 = schema 文档 + crypto 规格 + 解密器跑通语料库 + 差分报告。
- **Phase 2（里程碑）**：差分校验台对 collector 端点的「接受率」从 0 显著上升；度量 = 每 N 次 solve 拿到 `_px3` 的比例。
- **Phase 3（里程碑）**：E2E 注册成功率（全 HTTP，无浏览器长按）。
- 单元测试：各组件独立可测（`SampleCorpus` 读写、`HookInjector` 注入、`PayloadDecryptor` 对黄金样本解密、`SchemaDiffer` 对构造样本 diff）。遵循现有 pytest 约定（不新增 conftest/pytest.ini/__init__，用 asyncio.run 包装）。

## 11. 参考

- 现成逆向参照：`github.com/Pr0t0ns/PerimeterX-Reverse`、The Lab #42/#56（thewebscraping.club）。
- 协议事实来源：HUMAN edocs（collector 端点）、webscraping.wiki、roundproxies、thedatascientist（press-and-hold 行为信号）、hybrid-analysis 样本（hsprotect.net app_id=PXzC5j78di 坐实 PerimeterX）。
- 本仓 Arkose 同款范式参照：`_funcaptcha_solver/`（reversed BDA、纯 HTTP）。
