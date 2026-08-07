# 海洋微光主题 + 主题架构重构 设计文档

日期：2026-06-14
范围：整体视觉改造 + 打通 antd（用户确认）

## 背景与问题

前端（React + antd + Vite）已有基于 CSS 变量的主题系统（`frontend/src/theme/`），内置
light / dark / cyberpunk / terminal 四套，可在「设置 → 主题」切换。存在两个问题：

1. **主题半残**：`global.css` 的 `:root` 定义了约 40 个 CSS 变量，而 `ThemeProvider`
   切主题时只覆盖 `tokens.ts` 里的 12 个。`--bg-elevated` / `--text-muted` /
   `--text-bright` / `--accent-dim/soft` / `--border-bright` / 各 `-soft`/`-dim`
   柔光色从不随主题变化，切到暗色系时表头、次级文字、选中态仍是亮色值，颜色割裂。
2. **antd 未接主题**：`main.tsx` 的 `ConfigProvider` 只配了 `locale`，没有 `theme`
   算法。没被 `.ant-*` CSS 覆盖的组件（Dropdown / DatePicker 面板 / Drawer /
   Message / Checkbox 等）不跟随主题明暗与强调色。

## 目标

- 新增「海洋微光 Ocean」亮色主题并设为默认。
- 修复半残问题：所有主题（含旧 4 套）获得完整、协调的变量集。
- 打通 antd：`ConfigProvider` 按主题明暗选算法、映射强调色与圆角。

## 架构（设计模式）

```
frontend/src/theme/
  palette.ts        # Palette 接口 + ThemeName/ThemeMode 类型（核心调色板 ~14 值）
  buildTokens.ts    # Factory + Strategy：核心色 → 完整 CSS 变量集（含派生色）
  antdAdapter.ts    # Adapter：Palette → antd ThemeConfig
  registry.ts       # Registry：主题注册表 + themeList + DEFAULT_THEME
  themes/
    ocean.ts        # 🌊 新增，默认
    light.ts dark.ts cyberpunk.ts terminal.ts  # 改写为紧凑 Palette
  ThemeProvider.tsx # 应用全部 CSS 变量 + 包裹 antd ConfigProvider(locale+theme)
```

- **Registry 模式**：`registry.ts` 为主题唯一真源。新增主题只改此处，`SettingsPage`
  色块改为从注册表读取，消除设置页里硬编码的主题列表重复。
- **Factory + Strategy**：`buildCssVars(palette)` 把约 14 个核心色派生为完整变量集。
  `-dim`/`-soft` 用 alpha；`-elevated`/`-muted`/`-bright`/`-border-bright` 按
  `mode` 选明/暗两套混色策略（亮色朝黑混、暗色朝白混）。一次修掉半残问题。
- **Adapter 模式**：`toAntdConfig(palette)` 按 `mode` 选 `defaultAlgorithm` /
  `darkAlgorithm`，把核心色映射到 `colorPrimary` / `colorBgBase` / `colorBgContainer`
  / `colorText` / `borderRadius` 等。CSS 覆盖层负责精修主表面，antd 算法兜底长尾组件。

## 海洋微光 Ocean 调色板（默认，亮色，mode=light）

| 字段 | 值 |
|---|---|
| bg | `#f0f9ff` |
| card / sidebar | `#ffffff` |
| sidebarIcon | `#e0f2fe` |
| text | `#0f172a` |
| textSecondary | `#64748b` |
| border | `#e2e8f0` |
| accent | `#0891b2` |
| success / error / warning | `#16a34a` / `#dc2626` / `#ea580c` |
| radius | `10px` |

字体、阴影、`--radius-lg` 主题无关，保留在 `global.css :root` 不随主题变。

## 接线改动

- `ThemeProvider` 内置 antd `ConfigProvider`（`locale=zhCN` + `theme=toAntdConfig`）；
  `main.tsx` 移除其原 `ConfigProvider`，合并为一处。
- `global.css :root` 默认值换成 Ocean（含派生色），作 JS 执行前首屏兜底，避免闪烁。
- `MainLayout.module.css` 的 Logo 紫色硬编码渐变改为 `var(--accent)→var(--accent-light)`。
- 默认主题 `DEFAULT_THEME='ocean'`；已存 localStorage 的用户保留其选择。
- 删除不再使用的 `theme/tokens.ts`（`ThemeTokens` 被 `Palette` 取代）。

## 派生策略（buildTokens）

- `--bg-card-hover`：暗→朝白 4%，亮→朝文字 2%
- `--bg-input`：暗→朝黑 12%，亮→= bg
- `--bg-elevated`：暗→朝白 6%，亮→bg 朝文字 5%
- `--bg-*-soft`：rgba(色, 暗 0.16 / 亮 0.10)
- `--text-muted`：textSecondary 朝 bg 混 35%
- `--text-bright`：暗→朝白 15%，亮→朝黑 20%
- `--border-bright`：暗→朝白 18%，亮→朝文字 22%
- `--accent-light`：朝白 14~16%
- `--accent-dim`/`-soft`/`--*-dim`：对应色 alpha 0.08 / 0.12(暗0.16)

## 测试与验证

- `npm run build`（tsc + vite）确保类型与编译通过。
- `npm test`：现有 `SettingsPage.test.tsx` 只断言「主题」Tab 存在，不查色块，预期不破。
  `renderWithProviders` 经 `ThemeProvider` → 现在也带 antd `ConfigProvider`，需确认通过。
- 人工：重启 vite + 清 `.vite` 缓存（Windows 上 Edit 后常给缓存旧码），逐主题核对
  亮色长表格、暗色系不再割裂、antd 下拉/弹窗跟随主题。

## 取舍

- 圆角保持 10px（不改 12）。
- 旧 4 套主题一并经 `buildCssVars` 修成完整协调（推荐项，几乎不加量且修既有 bug）。
