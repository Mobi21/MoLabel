import { create } from 'zustand'

export interface Workspace {
  id: string
  name: string
  slug: string
  rootPath: string
  datasetCount: number
  workflowCount: number
}

interface WorkspaceState {
  activeWorkspace: Workspace | null
  workspaces: Workspace[]
  setActiveWorkspace: (ws: Workspace) => void
  setWorkspaces: (wss: Workspace[]) => void
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  activeWorkspace: null,
  workspaces: [],
  setActiveWorkspace: (ws) => set({ activeWorkspace: ws }),
  setWorkspaces: (wss) => set({ workspaces: wss }),
}))
