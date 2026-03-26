import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface UIState {
  theme: 'light' | 'dark'
  sidebarCollapsed: boolean
  assistantOpen: boolean
  toggleTheme: () => void
  setSidebarCollapsed: (v: boolean) => void
  toggleAssistant: () => void
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      theme: 'dark',
      sidebarCollapsed: false,
      assistantOpen: false,
      toggleTheme: () =>
        set((s) => {
          const next = s.theme === 'dark' ? 'light' : 'dark'
          document.documentElement.classList.toggle('dark', next === 'dark')
          return { theme: next }
        }),
      setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
      toggleAssistant: () => set((s) => ({ assistantOpen: !s.assistantOpen })),
    }),
    { name: 'molabel-ui' },
  ),
)
