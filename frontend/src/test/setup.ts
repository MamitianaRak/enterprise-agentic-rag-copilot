import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest'
import { useAuthStore } from '@/stores/auth-store'
import { ADMIN_USER, handlers } from './handlers'

export const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
// Tests start signed in as an admin who can use every domain; auth tests sign out first.
beforeEach(() => useAuthStore.getState().signIn('test-token', ADMIN_USER))
afterEach(() => {
  server.resetHandlers()
  cleanup()
  useAuthStore.getState().signOut()
  localStorage.clear()
})
afterAll(() => server.close())

// jsdom gaps
Element.prototype.scrollIntoView = () => {}
window.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: () => {},
  removeEventListener: () => {},
  addListener: () => {},
  removeListener: () => {},
  dispatchEvent: () => false,
})) as typeof window.matchMedia
