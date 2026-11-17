import { useQuery } from '@tanstack/react-query'
import { listQueuesEndpointQueryKey } from '@/api/generated/@tanstack/react-query.gen'
import { queuesQuery } from '@/api/queries'
import type { QueueSummary } from '@/api/generated/types.gen'
import { useReviewer } from '@/features/session/session'

export function useQueues() {
  return useQuery(queuesQuery(useReviewer().workspace_id))
}

/** Every cached queue list, which a submit or skip changes. */
export const queuesKey = listQueuesEndpointQueryKey()

export function useQueue(queueId: string): QueueSummary | undefined {
  return useQueues().data?.items.find((q) => q.queue_id === queueId)
}

export function queueTitle(queue: QueueSummary): string {
  return queue.task_schema_title ?? 'Untitled task schema'
}

/** Gold answers a calibration queue's items, so it has nothing to adjudicate. */
export function isAdjudicable(queue: QueueSummary): boolean {
  return queue.kind !== 'calibrate'
}

export function isBlind(queue: QueueSummary): boolean {
  return queue.blind_review_policy === 'hide_agent_outputs_by_default'
}

const KIND_LABELS: Record<NonNullable<QueueSummary['kind']>, string> = {
  review: 'Review',
  triage: 'Triage',
  calibrate: 'Calibration',
  adjudicate: 'Adjudication',
}

export function kindLabel(queue: QueueSummary): string {
  return queue.kind ? KIND_LABELS[queue.kind] : 'Queue'
}
