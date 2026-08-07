export type ThemeName = 'ocean' | 'light' | 'dark' | 'cyberpunk' | 'terminal'
export type ThemeMode = 'light' | 'dark'

/**
 * 一套主题的「核心调色板」——仅声明语义色与基础属性。
 * 完整的 ~40 个 CSS 变量由 buildTokens.buildCssVars 派生。
 */
export interface Palette {
  name: ThemeName
  label: string
  icon: string
  mode: ThemeMode
  bg: string
  card: string
  sidebar: string
  sidebarIcon: string
  text: string
  textSecondary: string
  border: string
  accent: string
  success: string
  error: string
  warning: string
  radius: string
}
