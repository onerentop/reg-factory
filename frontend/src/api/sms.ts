import apiClient from './client'

export interface SmsProvider {
  name: string
  display_name: string
  config_schema: Record<string, any>
}

export interface PlatformConfig {
  provider_name: string
  display_name: string
  enabled: string
  priority: number
  config: Record<string, any>
}

export const smsApi = {
  listProviders: () =>
    apiClient.get('/sms/providers'),

  getBalance: (name: string) =>
    apiClient.get(`/sms/providers/${name}/balance`),

  getConfigs: () =>
    apiClient.get('/sms/config'),

  saveConfig: (providerName: string, data: Partial<PlatformConfig>) =>
    apiClient.put(`/sms/config/${providerName}`, data),
}
