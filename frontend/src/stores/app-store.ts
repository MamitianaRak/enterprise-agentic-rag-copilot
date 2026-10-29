// UI preferences shared across components. Domain and conversation live in the URL instead.
import { create } from 'zustand'
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware'

export type Theme = 'light' | 'dark' | 'system'

interface AppState {
  theme: Theme
  sidebarOpen: boolean // mobile drawers
  inspectorOpen: boolean
  setTheme: (theme: Theme) => void
  setSidebarOpen: (open: boolean) => void
  setInspectorOpen: (open: boolean) => void
}

// localStorage can throw (private mode, blocked storage): fall back to no persistence.
export const safeStorage: StateStorage = {
  getItem: (name) => {
    try {
      return localStorage.getItem(name)
    } catch {
      return null
    }
  },
  setItem: (name, value) => {
    try {
      localStorage.setItem(name, value)
    } catch {
      /* ignore */
    }
  },
  removeItem: (name) => {
    try {
      localStorage.removeItem(name)
    } catch {
      /* ignore */
    }
  },
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      theme: 'system',
      sidebarOpen: false,
      inspectorOpen: false,
      setTheme: (theme) => set({ theme }),
      setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
      setInspectorOpen: (inspectorOpen) => set({ inspectorOpen }),
    }),
    {
      name: 'enterprise-copilot',
      storage: createJSONStorage(() => safeStorage),
      partialize: (state) => ({ theme: state.theme }),
    },
  ),
)
