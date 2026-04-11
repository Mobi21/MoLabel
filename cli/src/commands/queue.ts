import type { Command } from 'commander'

import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import { buildClient, getRuntimeOptions, outputMode } from './context.js'

export function registerQueueCommands(program: Command, runtime: CliRuntimeOptions): void {
  const queue = program.command('queue').description('Queue operations')

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

async function runQueueStatus(options: CliRuntimeOptions, queueId: string): Promise<void> {
  const client = await requireClient(options, 'queue status')
  const response = await client.getJson<Record<string, unknown>>(
    `/api/v1/queues/${encodeURIComponent(queueId)}/status`,
  )
  await emit(response, outputMode(options))
}

async function runQueueClaim(options: CliRuntimeOptions, queueId: string): Promise<void> {
  const client = await requireClient(options, 'queue claim')
  const response = await client.postJson<Record<string, unknown>>(
    `/api/v1/queues/${encodeURIComponent(queueId)}/claim`,
    {},
  )
  await emit(response, outputMode(options))
}

async function runQueueReviewers(options: CliRuntimeOptions): Promise<void> {
  const client = await requireClient(options, 'queue reviewers')
  const response = await client.getJson<Record<string, unknown>>(
    '/api/v1/mission-control/reviewers',
  )
  await emit(response, outputMode(options))
}

async function requireClient(
  options: CliRuntimeOptions,
  commandName: string,
): Promise<NonNullable<Awaited<ReturnType<typeof buildClient>>>> {
  const client = await buildClient(options)
  if (!client) {
    throw new Error(`${commandName} requires --base-url or MOLABEL_BASE_URL`)
  }
  return client
}
