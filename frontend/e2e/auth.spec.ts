import { test, expect } from '@playwright/test'

// E2E：前端↔后端真链路。后端 gateway 已种子 admin/admin123。
// vite dev 把 /api 代理到 gateway(8000)。

test('登录成功：admin 登录后跳转 dashboard 并加载', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('用户名').fill('admin')
  await page.getByPlaceholder('密码').fill('admin123')
  await page.locator('button[type="submit"]').click()

  // 真链路：fetch /api/auth/login → gateway 校验 → access_token → 跳 /dashboard
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })
  await expect(page.getByText('仪表盘')).toBeVisible({ timeout: 10000 })

  // token 已落 localStorage
  const token = await page.evaluate(() => localStorage.getItem('token'))
  expect(token).toBeTruthy()
})

test('登录失败：错误密码留在登录页', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('用户名').fill('admin')
  await page.getByPlaceholder('密码').fill('wrong-password')
  await page.locator('button[type="submit"]').click()

  await page.waitForTimeout(2500)
  await expect(page).not.toHaveURL(/\/dashboard/)
})
