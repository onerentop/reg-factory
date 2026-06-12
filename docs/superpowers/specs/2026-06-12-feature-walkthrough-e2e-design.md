# 功能真实走一遍（UI E2E walkthrough）设计

- 日期：2026-06-12
- 目标：用 Playwright 经**真实 UI** 逐功能**真操作**运行栈，验真实结果——比单测/路由/冒烟更进一步的端到端验收。
- 决策：UI E2E 真操作；**全真触发**（含真 SMS/真注册——如实暴露外部门槛）。
- 前提：运行栈(gateway+services+redis+worker)在跑、gateway 已种子 admin、Playwright+chromium 已装、vite dev 由 webServer 自起。

## 1. 真实前提（诚实交代）

| 功能 | 真走能到哪 |
|---|---|
| 纯DB(账号/代理增删改/config/告警/导入/用户) | **真完成 + 验 DB 持久化** |
| proxy test | 真连配置的代理，**如实记录连通结果**(可能失败) |
| SMS 取号 | 需有余额 provider；没配则**如实记录"无provider/余额"** |
| 注册 | 真触发 worker→真开 ixBrowser；干净 IP 烧了则**如实卡长按 gate**(不真出号) |

→ walkthrough 如实暴露每个功能真实落点，不掩盖门槛。

## 2. 结构

```
e2e/_helpers.ts          : login(page) + 复用工具(导航/等待toast)
e2e/walkthrough/auth.spec.ts          : 登录(已有) + 建用户→列表出现
e2e/walkthrough/accounts.spec.ts      : 建/删账号→列表真出现/消失(可 API 复核 DB)
e2e/walkthrough/proxy.spec.ts         : 加代理→出现→test(真连,记结果)→改→删→消失
e2e/walkthrough/config.spec.ts        : 设config→查到→(回滚)
e2e/walkthrough/alerts.spec.ts        : 建告警规则→列表出现→删
e2e/walkthrough/sms.spec.ts           : 配provider→保存→(查余额/取号:真外部结果)
e2e/walkthrough/import.spec.ts        : 导入账号→真导入→账号出现
e2e/walkthrough/registration.spec.ts  : 点"新建注册"→任务触发→记录入队/卡gate
e2e/walkthrough/observability.spec.ts : dashboard/audit/logs 显示上面操作的真数据
```

## 3. 每 spec 的"真走+验"模式

- **真操作**：经 UI 点按钮/填表单/提交(Playwright `getByPlaceholder`/`getByRole`/`locator`；antd 2字按钮用 `button[type=submit]` 或正则)。
- **验真实结果**：① UI 上结果出现/消失(`expect(...).toBeVisible()`)；② 必要时经 gateway API 复核 DB 真持久化(`page.request.get(...)` 或 fetch)。
- **门槛功能**：触发后**断言"真触发了"**(任务入队/请求发出/真外部返回)，对失败结果**如实断言其为门槛态**(不当 FAIL，记 GATED)，并在测试名/注释标明。
- **清理**：建的测试数据(账号/代理/规则)真删除，walkthrough 可重复跑。

## 4. 验证 / 输出

- `cd frontend && npm run test:e2e` 全部通过(纯DB功能真完成;门槛功能真触发+如实记录)。
- 每个功能一条结果:真完成 / 真触发到门槛。
- 注册若拿到干净 IP→可真出号;否则如实显示卡 gate。

## 5. 非目标

- 不 mock 任何后端(全真链路)。
- 不替代已有单测/路由测试(这是验收层)。
- 不为真出号强求 ixBrowser/IP——如实记录其门槛态即可。
