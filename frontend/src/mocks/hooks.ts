import { useQuery } from '@tanstack/react-query'
import {
  mockWorkspace,
  mockDatasets,
  mockDashboardStats,
  mockWorkflows,
  mockTaskSchemas,
  mockAgentRuns,
  mockReviewQueue,
  mockQualityMetrics,
  mockPlugins,
  mockReviewers,
  mockActivity,
  mockExports,
} from './data'

export function useWorkspace() {
  return useQuery({
    queryKey: ['workspace'],
    queryFn: () => Promise.resolve(mockWorkspace),
  })
}

export function useDatasets() {
  return useQuery({
    queryKey: ['datasets'],
    queryFn: () => Promise.resolve(mockDatasets),
  })
}

export function useDashboardStats() {
  return useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: () => Promise.resolve(mockDashboardStats),
  })
}

export function useWorkflows() {
  return useQuery({
    queryKey: ['workflows'],
    queryFn: () => Promise.resolve(mockWorkflows),
  })
}

export function useTaskSchemas() {
  return useQuery({
    queryKey: ['task-schemas'],
    queryFn: () => Promise.resolve(mockTaskSchemas),
  })
}

export function useAgentRuns() {
  return useQuery({
    queryKey: ['agent-runs'],
    queryFn: () => Promise.resolve(mockAgentRuns),
  })
}

export function useReviewQueue() {
  return useQuery({
    queryKey: ['review-queue'],
    queryFn: () => Promise.resolve(mockReviewQueue),
  })
}

export function useQualityMetrics() {
  return useQuery({
    queryKey: ['quality-metrics'],
    queryFn: () => Promise.resolve(mockQualityMetrics),
  })
}

export function usePlugins() {
  return useQuery({
    queryKey: ['plugins'],
    queryFn: () => Promise.resolve(mockPlugins),
  })
}

export function useReviewers() {
  return useQuery({
    queryKey: ['reviewers'],
    queryFn: () => Promise.resolve(mockReviewers),
  })
}

export function useActivity() {
  return useQuery({
    queryKey: ['activity'],
    queryFn: () => Promise.resolve(mockActivity),
  })
}

export function useExports() {
  return useQuery({
    queryKey: ['exports'],
    queryFn: () => Promise.resolve(mockExports),
  })
}
