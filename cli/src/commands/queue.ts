import type { Command } from 'commander'

import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import { getRuntimeOptions, outputMode, requireClient } from './context.js'

export function registerQueueCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const queue = program.command('queue').description('Queue operations')

  queue
    .command('list')
    .description("List the review queues of the session's workspace")
    .option(
      '--workspace-id <id>',
      "The session's workspace. Any other fails with HTTP_404",
    )
    .action(async function (this: Command) {
      await runQueueList(
        getRuntimeOptions(program, runtime),
        this.opts<{ workspaceId?: string }>().workspaceId,
      )
    })

  queue
    .command('status <queue-id>')
    .description('Show the status of a review queue')
    .action(async (queueId: string) => {
      await runQueueStatus(getRuntimeOptions(program, runtime), queueId)
    })

  queue
    .command('claim <queue-id>')
    .description('Claim the next available item from a queue')
    .action(async (queueId: string) => {
      await runQueueClaim(getRuntimeOptions(program, runtime), queueId)
    })

  queue
    .command('close-copies <queue-id>')
    .description(
      'Close the unclaimed copies of a queue, so review ends with the copies in',
    )
    .action(async (queueId: string) => {
      await runQueueCloseCopies(getRuntimeOptions(program, runtime), queueId)
    })

  queue
    .command('reviewers')
    .description('Show mission-control reviewer visibility')
    .action(async () => {
      await runQueueReviewers(getRuntimeOptions(program, runtime))
    })

  queue
    .command('mission-control')
    .description('Alias for queue reviewers')
    .action(async () => {
      await runQueueReviewers(getRuntimeOptions(program, runtime))
    })
}

async function runQueueList(
  options: CliRuntimeOptions,
  workspaceId?: string,
): Promise<void> {
  const client = await requireClient(options, 'queue list')
  const query = workspaceId
    ? `?${new URLSearchParams({ workspace_id: workspaceId }).toString()}`
    : ''
  const response = await client.getJson(`/api/v1/queues${query}`)
  await emit(response, outputMode(options))
}

async function runQueueStatus(
  options: CliRuntimeOptions,
  queueId: string,
): Promise<void> {
  const client = await requireClient(options, 'queue status')
  const response = await client.getJson(
    `/api/v1/queues/${encodeURIComponent(queueId)}/status`,
  )
  await emit(response, outputMode(options))
}

async function runQueueClaim(
  options: CliRuntimeOptions,
  queueId: string,
): Promise<void> {
  const client = await requireClient(options, 'queue claim')
  const response = await client.postJson(
    `/api/v1/queues/${encodeURIComponent(queueId)}/claim`,
    {},
  )
  await emit(response, outputMode(options))
}

async function runQueueCloseCopies(
  options: CliRuntimeOptions,
  queueId: string,
): Promise<void> {
  const client = await requireClient(options, 'queue close-copies')
  const response = await client.postJson(
    `/api/v1/queues/${encodeURIComponent(queueId)}/close-copies`,
    {},
  )
  await emit(response, outputMode(options))
}

async function runQueueReviewers(options: CliRuntimeOptions): Promise<void> {
  const client = await requireClient(options, 'queue reviewers')
  const response = await client.getJson('/api/v1/mission-control/reviewers')
  await emit(response, outputMode(options))
}
