import axios, { AxiosError } from 'axios'
import { useAuthStore } from '@/stores/auth-store'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** FastAPI sends `detail` as a string, or as a list of validation errors (422). */
export function detailMessage(detail: unknown, status: number): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? String(d)).join('; ')
  return status ? `Request failed (${status})` : 'Cannot reach the server. Is the backend running?'
}

/**
 * Backend origin, baked in at build time. Empty in development and docker compose, where the
 * API is served on the same origin (Vite proxy / nginx); set when the frontend is hosted on its
 * own, e.g. VITE_API_BASE_URL=https://enterprise-copilot-api.onrender.com on Render.
 */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

export const http = axios.create({ baseURL: `${API_BASE_URL}/api` })

/** Authorization header of the signed-in user, if any. */
export function authHeader(): Record<string, string> {
  const token = useAuthStore.getState().token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** A 401 means the session is gone (expired, revoked): sign out, the router shows the login page. */
export function handleUnauthorized(status: number) {
  if (status === 401 && useAuthStore.getState().token) useAuthStore.getState().signOut()
}

http.interceptors.request.use((config) => {
  Object.entries(authHeader()).forEach(([name, value]) => config.headers.set(name, value))
  return config
})

// Every failed request becomes an ApiError with a human-readable message.
http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: unknown }>) => {
    const status = error.response?.status ?? 0
    handleUnauthorized(status)
    return Promise.reject(new ApiError(status, detailMessage(error.response?.data?.detail, status)))
  },
)
