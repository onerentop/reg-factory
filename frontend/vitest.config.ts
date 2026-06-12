import { defineConfig, configDefaults } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // e2e/ 下是 Playwright 规范(用 @playwright/test 的 test API)，不能被 vitest 收集
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
})
