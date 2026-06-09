import apiClient from './client'

export interface Account {
  id: string
  email: string
  platform: string
  status: string
  current_step: number
  total_steps: number
  error_message?: string
  proxy_used?: string
  created_at?: string
  steps: Step[]
}

export interface Step {
  step_number: number
  name: string
  status: string
  error_message?: string
  duration_ms?: number
}

export interface AccountListParams {
  platform?: string
  status?: string
  keyword?: string
  page?: number
  page_size?: number
}

export const accountApi = {
  list: (params: AccountListParams) =>
    apiClient.get('/accounts', { params }),

  get: (id: string) =>
    apiClient.get(`/accounts/${id}`),

  create: (data: { email: string; platform: string; password?: string }) =>
    apiClient.post('/accounts', data),

  update: (id: string, data: Partial<Account>) =>
    apiClient.put(`/accounts/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/accounts/${id}`),

  batchDelete: (ids: string[]) =>
    apiClient.post('/accounts/batch/delete', { account_ids: ids }),

  batchExport: (data: { account_ids?: string[]; format: string; platform?: string; status?: string }) =>
    apiClient.post('/accounts/batch/export', data),

  batchRetry: (ids: string[]) =>
    apiClient.post('/accounts/batch/retry', { account_ids: ids }),

  getSteps: (id: string) =>
    apiClient.get(`/accounts/${id}/steps`),

  importAccounts: (data: { platform: string; format: string; content: string }) =>
    apiClient.post('/accounts/import', data),
}
