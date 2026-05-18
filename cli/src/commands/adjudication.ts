import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import type { Command } from 'commander'

import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import { buildClient, getRuntimeOptions, outputMode } from './context.js'

type JsonObject = Record<string, unknown>

export function registerAdjudicationCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const adjudication = program
    .command('adjudication')
    .description('Adjudication operations')

  adjudication
    .command('queue')
    .description('Show the current adjudication queue')
    .action(async () => {
      await runAdjudicationQueue(getRuntimeOptions(program, runtime))
    })

  adjudication
    .command('detect')
    .description('Detect disagreements from review events')
    .option('--task-schema-id <id>')
    .option('--events-json <json>')
    .option('--events-file <path>')
    .action(async function (this: Command) {
      const options = this.opts<{
        taskSchemaId?: string
        eventsJson?: string
        eventsFile?: string
      }>()
      await runAdjudicationDetect(
        getRuntimeOptions(program, runtime),
        options.taskSchemaId,
        options.eventsJson,
        options.eventsFile,
      )
    })

  adjudication
    .command('build')
    .description('Detect disagreements and build an adjudication queue')
    .option('--task-schema-id <id>')
    .option('--events-json <json>')
    .option('--events-file <path>')
    .action(async function (this: Command) {
      const options = this.opts<{
        taskSchemaId?: string
        eventsJson?: string
        eventsFile?: string
      }>()
      await runAdjudicationBuild(
        getRuntimeOptions(program, runtime),
        options.taskSchemaId,
        options.eventsJson,
        options.eventsFile,
      )
    })

  adjudication
    .command('resolve <queue-item-id>')
    .description('Resolve an adjudication queue item')
    .option('--resolution <resolution>')
    .option('--resolved-labels-json <json>')
    .option('--resolved-labels-file <path>')
    .option('--rationale <text>')
    .action(async function (this: Command, queueItemId: string) {
      const options = this.opts<{
        resolution?: string
        resolvedLabelsJson?: string
        resolvedLabelsFile?: string
        rationale?: string
      }>()
      await runAdjudicationResolve(
        getRuntimeOptions(program, runtime),
        queueItemId,
        options.resolution,
        options.resolvedLabelsJson,
        options.resolvedLabelsFile,
        options.rationale,
      )
    })
}

async function runAdjudicationQueue(options: CliRuntimeOptions): Promise<void> {
  const client = await requireClient(options, 'adjudication queue')
  const response = await client.getJson('/api/v1/adjudication/queue')
  await emit(response, outputMode(options))
}

async function runAdjudicationDetect(
  options: CliRuntimeOptions,
  taskSchemaId?: string,
  eventsJson?: string,
  eventsFile?: string,
): Promise<void> {
  const client = await requireClient(options, 'adjudication detect')
  const response = await client.postJson(
    '/api/v1/adjudication/detect',
    await buildEventsBody(taskSchemaId, eventsJson, eventsFile),
  )
  await emit(response, outputMode(options))
}

async function runAdjudicationBuild(
  options: CliRuntimeOptions,
  taskSchemaId?: string,
  eventsJson?: string,
  eventsFile?: string,
): Promise<void> {
  const client = await requireClient(options, 'adjudication build')
  const response = await client.postJson(
    '/api/v1/adjudication/queue/build',
    await buildEventsBody(taskSchemaId, eventsJson, eventsFile),
  )
  await emit(response, outputMode(options))
}

async function runAdjudicationResolve(
  options: CliRuntimeOptions,
  queueItemId: string,
  resolution?: string,
  resolvedLabelsJson?: string,
  resolvedLabelsFile?: string,
  rationale?: string,
): Promise<void> {
  if (!resolution) {
    throw new Error('adjudication resolve requires --resolution')
  }
  const client = await requireClient(options, 'adjudication resolve')
  const body: JsonObject = {
    queue_item_id: queueItemId,
    resolution,
    rationale: rationale ?? null,
  }
  const resolvedLabels = await readOptionalJsonObject(
    resolvedLabelsJson,
    resolvedLabelsFile,
  )
  if (resolvedLabels) {
    body.resolved_labels = resolvedLabels
  }
  const response = await client.postJson('/api/v1/adjudication/resolve', body)
  await emit(response, outputMode(options))
}

async function buildEventsBody(
  taskSchemaId?: string,
  eventsJson?: string,
  eventsFile?: string,
): Promise<JsonObject> {
  if (!taskSchemaId) {
    throw new Error('--task-schema-id is required')
  }
  const reviewEventsByRecord = await readOptionalJsonObject(
    eventsJson,
    eventsFile,
  )
  if (!reviewEventsByRecord) {
    throw new Error('Provide --events-json, --events-file, or piped JSON input')
  }
  return {
    task_schema_id: taskSchemaId,
    review_events_by_record: reviewEventsByRecord,
  }
}

async function readOptionalJsonObject(
  jsonText?: string,
  filePath?: string,
): Promise<JsonObject | null> {
  if (filePath) {
    return readJsonObjectFromText(await readFile(resolve(filePath), 'utf8'))
  }
  if (jsonText) {
    return readJsonObjectFromText(jsonText)
  }
  return null
}

function readJsonObjectFromText(text: string): JsonObject {
  const parsed = JSON.parse(text) as unknown
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Expected a JSON object')
  }
  return parsed as JsonObject
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
