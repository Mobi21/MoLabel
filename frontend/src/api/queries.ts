import { queryOptions, type QueryClient } from '@tanstack/react-query'
import {
  getAgreementMetricsQueryKey,
  getCalibrationReportQueryKey,
  getGoldSetQueryKey,
  getMeQueryKey,
  getQueueDisagreementQueryKey,
  getReviewTaskEndpointQueryKey,
  getTaskSchemaQueryKey,
  listMyQueueTasksEndpointQueryKey,
  listGoldSetsEndpointQueryKey,
  listQueueDisagreementsQueryKey,
  listQueuesEndpointQueryKey,
  listReviewerProfilesQueryKey,
  listWorkspacesQueryKey,
} from '@/api/generated/@tanstack/react-query.gen'
import {
  getAgreementMetrics,
  getCalibrationReport,
  getGoldSet,
  getMe,
  getQueueDisagreement,
  getReviewTaskEndpoint,
  getTaskSchema,
  listGoldSetsEndpoint,
  listMyQueueTasksEndpoint,
  listQueueDisagreements,
  listQueuesEndpoint,
  listReviewerProfiles,
  listWorkspaces,
} from '@/api/generated/sdk.gen'

/*
 * Query options over the generated SDK, keyed by the generated query keys.
 * The TanStack plugin's own option factories are declared without
 * exactOptionalPropertyTypes, so their types do not fit useQuery under this
 * app's flags. Its mutation factories and keys do, and are used as is.
 */

export const meQuery = () =>
  queryOptions({
    queryKey: getMeQueryKey(),
    queryFn: async ({ signal }) =>
      (await getMe({ signal, throwOnError: true })).data,
    staleTime: Infinity,
  })

export const reviewerProfilesQuery = () =>
  queryOptions({
    queryKey: listReviewerProfilesQueryKey(),
    queryFn: async ({ signal }) =>
      (await listReviewerProfiles({ signal, throwOnError: true })).data,
  })

export const workspacesQuery = () => {
  const options = { query: { limit: 200 } }
  return queryOptions({
    queryKey: listWorkspacesQueryKey(options),
    queryFn: async ({ signal }) =>
      (await listWorkspaces({ ...options, signal, throwOnError: true })).data,
  })
}

export const queuesQuery = (workspaceId: string) => {
  const options = { query: { workspace_id: workspaceId } }
  return queryOptions({
    queryKey: listQueuesEndpointQueryKey(options),
    queryFn: async ({ signal }) =>
      (await listQueuesEndpoint({ ...options, signal, throwOnError: true }))
        .data,
  })
}

export const myTasksQuery = (queueId: string) => {
  const options = { path: { queue_id: queueId } }
  return queryOptions({
    queryKey: listMyQueueTasksEndpointQueryKey(options),
    queryFn: async ({ signal }) =>
      (
        await listMyQueueTasksEndpoint({
          ...options,
          signal,
          throwOnError: true,
        })
      ).data,
  })
}

export const reviewTaskQuery = (taskId: string) => {
  const options = { path: { task_id: taskId } }
  return queryOptions({
    queryKey: getReviewTaskEndpointQueryKey(options),
    queryFn: async ({ signal }) =>
      (await getReviewTaskEndpoint({ ...options, signal, throwOnError: true }))
        .data,
  })
}

export const taskSchemaQuery = (taskSchemaId: string) => {
  const options = { path: { task_schema_id: taskSchemaId } }
  return queryOptions({
    queryKey: getTaskSchemaQueryKey(options),
    queryFn: async ({ signal }) =>
      (await getTaskSchema({ ...options, signal, throwOnError: true })).data,
    staleTime: Infinity,
  })
}

export const disagreementsQuery = (queueId: string) => {
  const options = { path: { queue_id: queueId } }
  return queryOptions({
    queryKey: listQueueDisagreementsQueryKey(options),
    queryFn: async ({ signal }) =>
      (await listQueueDisagreements({ ...options, signal, throwOnError: true }))
        .data,
  })
}

export const disagreementQuery = (queueId: string, recordId: string) => {
  const options = { path: { queue_id: queueId, record_id: recordId } }
  return queryOptions({
    queryKey: getQueueDisagreementQueryKey(options),
    queryFn: async ({ signal }) =>
      (await getQueueDisagreement({ ...options, signal, throwOnError: true }))
        .data,
  })
}

export const agreementQuery = (workspaceId: string, queueId: string) => {
  const options = { query: { workspace_id: workspaceId, queue_id: queueId } }
  return queryOptions({
    queryKey: getAgreementMetricsQueryKey(options),
    queryFn: async ({ signal }) =>
      (await getAgreementMetrics({ ...options, signal, throwOnError: true }))
        .data,
  })
}

export const calibrationReportQuery = (queueId: string) => {
  const options = { path: { queue_id: queueId } }
  return queryOptions({
    queryKey: getCalibrationReportQueryKey(options),
    queryFn: async ({ signal }) =>
      (await getCalibrationReport({ ...options, signal, throwOnError: true }))
        .data,
  })
}

export const goldSetsQuery = () =>
  queryOptions({
    queryKey: listGoldSetsEndpointQueryKey(),
    queryFn: async ({ signal }) =>
      (await listGoldSetsEndpoint({ signal, throwOnError: true })).data,
  })

export const goldSetQuery = (goldSetId: string) => {
  const options = { path: { gold_set_id: goldSetId } }
  return queryOptions({
    queryKey: getGoldSetQueryKey(options),
    queryFn: async ({ signal }) =>
      (await getGoldSet({ ...options, signal, throwOnError: true })).data,
  })
}

/** Mark stale the gold-set list and every set read, which a promotion changes. */
export function invalidateGoldSets(queryClient: QueryClient): void {
  for (const _id of ['listGoldSetsEndpoint', 'getGoldSet']) {
    void queryClient.invalidateQueries({ queryKey: [{ _id }] })
  }
}

/**
 * Mark stale what a submit, correction, skip or resolve changes: the queue's
 * agreement and calibration report, its disagreements, and the record's
 * disagreement.
 */
export function invalidateQueueOutcomes(
  queryClient: QueryClient,
  scope: { workspaceId: string; queueId: string; recordId: string },
): void {
  for (const queryKey of [
    agreementQuery(scope.workspaceId, scope.queueId).queryKey,
    calibrationReportQuery(scope.queueId).queryKey,
    disagreementsQuery(scope.queueId).queryKey,
    disagreementQuery(scope.queueId, scope.recordId).queryKey,
  ]) {
    void queryClient.invalidateQueries({ queryKey })
  }
}
