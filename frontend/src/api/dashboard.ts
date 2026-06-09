import apiClient from './client'

export const dashboardApi = {
  getData: () =>
    apiClient.get('/dashboard'),
}
