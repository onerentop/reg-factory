import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error.response?.data || error.message)
  }
)

export function installAuthorizedFetch() {
  const nativeFetch = window.fetch.bind(window)

  window.fetch = async (input, init = {}) => {
    const url = typeof input === 'string'
      ? input
      : input instanceof Request
        ? input.url
        : input.toString()
    const pathname = url.startsWith('/') ? url : new URL(url).pathname
    const isApiRequest = pathname.startsWith('/api/')
    const isLogin = pathname === '/api/auth/login'
    const token = localStorage.getItem('token')

    if (!isApiRequest || isLogin || !token) {
      return nativeFetch(input, init)
    }

    const requestHeaders = input instanceof Request ? input.headers : undefined
    const headers = new Headers(requestHeaders)
    new Headers(init.headers).forEach((value, key) => headers.set(key, value))
    if (!headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`)
    }
    const response = await nativeFetch(input, { ...init, headers })
    if (response.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return response
  }
}

export default apiClient
