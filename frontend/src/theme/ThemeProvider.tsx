import React, { createContext, useContext, useState, useEffect } from 'react'
import type { ThemeTokens } from './tokens'
import { lightTheme } from './themes/light'
import { darkTheme } from './themes/dark'

type ThemeName = 'light' | 'dark'

interface ThemeContextValue {
  theme: ThemeName
  setTheme: (name: ThemeName) => void
  tokens: ThemeTokens
}

const themes: Record<ThemeName, ThemeTokens> = { light: lightTheme, dark: darkTheme }

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'light',
  setTheme: () => {},
  tokens: lightTheme,
})

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<ThemeName>(
    () => (localStorage.getItem('theme') as ThemeName) || 'light'
  )

  const setTheme = (name: ThemeName) => {
    setThemeState(name)
    localStorage.setItem('theme', name)
  }

  useEffect(() => {
    const tokens = themes[theme]
    const root = document.documentElement
    Object.entries(tokens).forEach(([key, value]) => {
      root.style.setProperty(key, value)
    })
  }, [theme])

  return (
    <ThemeContext.Provider value={{ theme, setTheme, tokens: themes[theme] }}>
      {children}
    </ThemeContext.Provider>
  )
}

export const useTheme = () => useContext(ThemeContext)
