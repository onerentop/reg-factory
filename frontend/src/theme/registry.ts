import type { Palette, ThemeName } from './palette'
import { oceanTheme } from './themes/ocean'
import { lightTheme } from './themes/light'
import { darkTheme } from './themes/dark'
import { cyberpunkTheme } from './themes/cyberpunk'
import { terminalTheme } from './themes/terminal'

/** 主题唯一真源：新增主题只需在此注册。 */
export const themeRegistry: Record<ThemeName, Palette> = {
  ocean: oceanTheme,
  light: lightTheme,
  dark: darkTheme,
  cyberpunk: cyberpunkTheme,
  terminal: terminalTheme,
}

/** 设置页色块按此顺序渲染。 */
export const themeList: Palette[] = [
  oceanTheme,
  lightTheme,
  darkTheme,
  cyberpunkTheme,
  terminalTheme,
]

export const DEFAULT_THEME: ThemeName = 'ocean'
