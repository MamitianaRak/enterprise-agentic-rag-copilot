// The signed-in user and their session token. The token is kept in localStorage so a page
// reload keeps the session; the API re-reads the user's rights on every request anyway.
import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import type { SessionUser } from '@/api/schemas'
import { safeStorage } from './app-store'

interface AuthState {
  token: string | null
  user: SessionUser | null
  signIn: (token: string, user: SessionUser) => void
  signOut: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      signIn: (token, user) => set({ token, user }),
      signOut: () => set({ token: null, user: null }),
    }),
    { name: 'enterprise-copilot-auth', storage: createJSONStorage(() => safeStorage) },
  ),
)
