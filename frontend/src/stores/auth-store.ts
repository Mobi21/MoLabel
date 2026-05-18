import { create } from 'zustand'

export interface Reviewer {
  id: string
  displayName: string
  avatarColor: string
  isOperator: boolean
}

interface AuthState {
  currentReviewer: Reviewer | null
  setCurrentReviewer: (r: Reviewer | null) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  currentReviewer: null,
  setCurrentReviewer: (r) => {
    set({ currentReviewer: r })
  },
}))
