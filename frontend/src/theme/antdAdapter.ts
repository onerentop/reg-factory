import { theme as antdTheme } from 'antd'
import type { ThemeConfig } from 'antd'
import type { Palette } from './palette'

/**
 * Adapter：把项目的 Palette 适配成 antd ThemeConfig。
 * 按 mode 选明/暗算法，让未被 .ant-* CSS 覆盖的长尾组件
 * （Dropdown / DatePicker 面板 / Drawer / Message 等）也跟随主题。
 */
export function toAntdConfig(p: Palette): ThemeConfig {
  return {
    algorithm: p.mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: {
      colorPrimary: p.accent,
      colorInfo: p.accent,
      colorSuccess: p.success,
      colorError: p.error,
      colorWarning: p.warning,
      colorBgBase: p.bg,
      colorBgContainer: p.card,
      colorBgElevated: p.card,
      colorBorder: p.border,
      colorText: p.text,
      colorTextSecondary: p.textSecondary,
      borderRadius: parseInt(p.radius, 10),
      fontFamily: "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    },
  }
}
