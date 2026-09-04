/**
 * client.ts interceptor tests
 *
 * vi.hoisted() runs before both vi.mock() factories and module imports,
 * so variables created there are safely accessible from inside the mock factory.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ── Create captured object in the hoisted zone ───────────────────────
const captured = vi.hoisted(() => ({
  requestHandler: undefined as ((config: any) => any) | undefined,
  responseSuccess: undefined as ((response: any) => any) | undefined,
  responseError: undefined as ((error: any) => Promise<any>) | undefined,
}))

// ── Axios mock ────────────────────────────────────────────────────────
vi.mock('axios', () => {
  const instance = {
    interceptors: {
      request: {
        use: (fn: (config: any) => any) => {
          captured.requestHandler = fn
        },
      },
      response: {
        use: (
          onFulfilled: (response: any) => any,
          onRejected: (error: any) => Promise<any>,
        ) => {
          captured.responseSuccess = onFulfilled
          captured.responseError = onRejected
        },
      },
    },
  }

  return {
    default: {
      create: () => instance,
    },
  }
})

// Importing client.ts causes its top-level code to run:
//   axios.create(...)  → returns the mock instance above
//   .interceptors.request.use(fn)  → captured.requestHandler = fn
//   .interceptors.response.use(ok, err) → captured.responseSuccess/Error = ...
import { installAuthorizedFetch } from '@/api/client'

// ── Stub window.location so assignment doesn't throw in jsdom ───────
Object.defineProperty(window, 'location', {
  value: { href: '' },
  writable: true,
})

// ─────────────────────────────────────────────────────────────────────
describe('request interceptor', () => {
  beforeEach(() => {
    localStorage.clear()
    ;(window.location as any).href = ''
  })

  it('injects Authorization header when token exists in localStorage', () => {
    localStorage.setItem('token', 'my-test-token')
    const config = { headers: {} as Record<string, string> }
    const result = captured.requestHandler!(config)
    expect(result.headers.Authorization).toBe('Bearer my-test-token')
  })

  it('omits Authorization header when no token in localStorage', () => {
    const config = { headers: {} as Record<string, string> }
    const result = captured.requestHandler!(config)
    expect(result.headers.Authorization).toBeUndefined()
  })

  it('returns the config object unchanged', () => {
    const config = { headers: {} as Record<string, string> }
    const result = captured.requestHandler!(config)
    expect(result).toBe(config)
  })
})

// ─────────────────────────────────────────────────────────────────────
describe('response interceptor – success path', () => {
  it('unwraps response.data', () => {
    const payload = { id: 1, name: 'test' }
    const response = { status: 200, data: payload }
    const result = captured.responseSuccess!(response)
    expect(result).toBe(payload)
  })

  it('returns primitive data as-is', () => {
    const response = { status: 200, data: 'ok' }
    expect(captured.responseSuccess!(response)).toBe('ok')
  })
})

// ─────────────────────────────────────────────────────────────────────
describe('response interceptor – error path', () => {
  beforeEach(() => {
    localStorage.clear()
    ;(window.location as any).href = ''
  })

  it('on 401: removes token from localStorage', async () => {
    localStorage.setItem('token', 'stale-token')
    const error = { response: { status: 401, data: { detail: 'Unauthorized' } } }
    await captured.responseError!(error).catch(() => {})
    expect(localStorage.getItem('token')).toBeNull()
  })

  it('on 401: redirects to /login', async () => {
    const error = { response: { status: 401, data: {} } }
    await captured.responseError!(error).catch(() => {})
    expect((window.location as any).href).toBe('/login')
  })

  it('on 401: rejects with response data', async () => {
    const errorData = { detail: 'Unauthorized' }
    const error = { response: { status: 401, data: errorData } }
    await expect(captured.responseError!(error)).rejects.toEqual(errorData)
  })

  it('on non-401 error: rejects with response data', async () => {
    const errorData = { detail: 'Not found' }
    const error = { response: { status: 404, data: errorData } }
    await expect(captured.responseError!(error)).rejects.toEqual(errorData)
  })

  it('on non-401 error: does NOT redirect', async () => {
    const error = { response: { status: 500, data: { detail: 'Server error' } } }
    await captured.responseError!(error).catch(() => {})
    expect((window.location as any).href).toBe('')
  })

  it('on non-401 error: does NOT clear localStorage token', async () => {
    localStorage.setItem('token', 'valid-token')
    const error = { response: { status: 500, data: {} } }
    await captured.responseError!(error).catch(() => {})
    expect(localStorage.getItem('token')).toBe('valid-token')
  })

  it('when error has no response: rejects with error.message', async () => {
    const error = { message: 'Network Error' }
    await expect(captured.responseError!(error)).rejects.toBe('Network Error')
  })
})

describe('authorized fetch compatibility adapter', () => {
  const originalFetch = window.fetch

  afterEach(() => {
    window.fetch = originalFetch
    localStorage.clear()
  })

  it('adds the bearer token to legacy /api fetch calls', async () => {
    const nativeFetch = vi.fn().mockResolvedValue(new Response())
    window.fetch = nativeFetch
    localStorage.setItem('token', 'legacy-token')

    installAuthorizedFetch()
    await window.fetch('/api/proxy', { method: 'GET' })

    expect(nativeFetch).toHaveBeenCalledOnce()
    const [, init] = nativeFetch.mock.calls[0]
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer legacy-token')
  })

  it('does not attach a token to the login request', async () => {
    const nativeFetch = vi.fn().mockResolvedValue(new Response())
    window.fetch = nativeFetch
    localStorage.setItem('token', 'legacy-token')

    installAuthorizedFetch()
    await window.fetch('/api/auth/login', { method: 'POST' })

    const [, init] = nativeFetch.mock.calls[0]
    expect(new Headers(init.headers).has('Authorization')).toBe(false)
  })

  it('preserves Request headers while adding authorization', async () => {
    const nativeFetch = vi.fn().mockResolvedValue(new Response())
    window.fetch = nativeFetch
    localStorage.setItem('token', 'legacy-token')

    installAuthorizedFetch()
    const request = new Request('http://localhost/api/proxy', {
      headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'request-1' },
    })
    await window.fetch(request)

    const [, init] = nativeFetch.mock.calls[0]
    const headers = new Headers(init.headers)
    expect(headers.get('Authorization')).toBe('Bearer legacy-token')
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(headers.get('X-Request-ID')).toBe('request-1')
  })
})
