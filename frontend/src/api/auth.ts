import apiClient from './client'

export const authApi = {
  login: (username: string, password: string) =>
    apiClient.post('/auth/login', { username, password }),

  listUsers: () =>
    apiClient.get('/auth/users'),

  createUser: (data: { username: string; password: string; role: string }) =>
    apiClient.post('/auth/users', data),

  listApiKeys: (ownerId?: string) =>
    apiClient.get('/auth/api-keys', { params: { owner_id: ownerId || 'system' } }),

  createApiKey: (data: { name: string; scopes: string[] }) =>
    apiClient.post('/auth/api-keys', data),

  revokeApiKey: (keyId: string) =>
    apiClient.delete(`/auth/api-keys/${keyId}`),
}
