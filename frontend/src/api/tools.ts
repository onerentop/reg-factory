import apiClient from './client'

// 工具/运维操作。apiClient 自动注入 token(避免 raw fetch 无 auth 静默失败)。
// apiClient 响应拦截器返回 response.data，即 { success, data, message }。
export const toolsApi = {
  unlockOutlook: (email: string, password: string) =>
    apiClient.post('/tools/unlock-outlook', { email, password }),

  validateKey: (key: string) =>
    apiClient.post('/tools/validate-keys', { key }),

  activatePlus: (access_token: string, email: string, card?: string) =>
    apiClient.post('/tools/activate-plus', { access_token, email, card: card || '' }),

  orchestrateAllPlatforms: (email: string, password: string, platforms: string[]) =>
    apiClient.post('/orchestrate/all-platforms', { email, password, platforms }),

  orchestrateFullFlow: (count: number, platforms: string[]) =>
    apiClient.post('/orchestrate/full-flow', { count, platforms }),
}
