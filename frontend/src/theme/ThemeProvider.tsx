import React, { createContext, useContext, useState, useEffect } from 'react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import type { Palette, ThemeName } from './palette'
import { themeRegistry, themeList, DEFAULT_THEME } from './registry'
import { buildCssVars } from './buildTokens'
import { toAntdConfig } from './antdAdapter'

interface ThemeContextValue {
  theme: ThemeName
  setTheme: (name: ThemeName) => void
  palette: Palette
  themes: Palette[]
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: DEFAULT_THEME,
  setTheme: () => {},
  palette: themeRegistry[DEFAULT_THEME],
  themes: themeList,
})

function getInitialTheme(): ThemeName {
  const saved = localStorage.getItem('theme') as ThemeName | null
  return saved && saved in themeRegistry ? saved : DEFAULT_THEME
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeName>(getInitialTheme)
  const palette = themeRegistry[theme]

  const setTheme = (name: ThemeName) => {
    setThemeState(name)
    localStorage.setItem('theme', name)
  }

  useEffect(() => {
    const root = document.documentElement
    Object.entries(buildCssVars(palette)).forEach(([key, value]) => {
      root.style.setProperty(key, value)
    })
  }, [palette])

  return (
    <ThemeContext.Provider value={{ theme, setTheme, palette, themes: themeList }}>
      <ConfigProvider locale={zhCN} theme={toAntdConfig(palette)}>
        {children}
      </ConfigProvider>
    </ThemeContext.Provider>
  )
}

export const useTheme = () => useContext(ThemeContext)
