import { defineConfig } from '@playwright/test'

// E2E：Playwright 驱动浏览器打 vite dev(3000)，vite 把 /api 代理到后端 gateway(8000)。
// 前提：后端栈(gateway+services+redis)已在运行；webServer 自动起前端 dev。
export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  fullyParallel: false,
  workers: 1, // walkthrough 真操作共享后端状态(建/删账号·代理·规则)，须顺序跑避免争用
  use: {
    baseURL: 'http://localhost:3000',
    headless: true,
    actionTimeout: 10000,
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: true,
    timeout: 60000,
  },
})
