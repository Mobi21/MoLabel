import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import type { Command } from 'commander'

import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import { getRuntimeOptions, outputMode, requireClient } from './context.js'

type JsonObject = Record<string, unknown>

interface ResolveOptions {
  reviewEventIds: string
  resolution?: string
  resolvedLabelsJson?: string
  resolvedLabelsFile?: string
  rationale?: string
}

export function registerAdjudicationCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const adjudication = program
    .command('adjudication')
    .description("Adjudicate the disagreements of a review queue's reviewers")

  adjudication
    .command('list <queue-id>')
    .description('List the records the reviewers of a queue disagree on')
    .action(async (queueId: string) => {
      const options = getRuntimeOptions(program, runtime)
      const client = await requireClient(options, 'adjudication list')
      await emit(
        await client.getJson(disagreementsPath(queueId)),
        outputMode(options),
      )
    })

  adjudication
    .command('show <queue-id> <record-id>')
    .description("Show a disagreement with every reviewer's labels")
    .action(async (queueId: string, recordId: string) => {
      const options = getRuntimeOptions(program, runtime)
      const client = await requireClient(options, 'adjudication show')
      await emit(
        await client.getJson(disagreementsPath(queueId, recordId)),
        outputMode(options),
      )
    })

  adjudication
    .command('resolve <queue-id> <record-id>')
    .description('Resolve a disagreement and store the outcome')
    .requiredOption(
      '--review-event-ids <ids>',
      'Comma-separated review_event_id of each reviewer_labels entry that adjudication show printed',
    )
    .option(
      '--resolution <resolution>',
      'resolve (the default), preserve_disagreement, downgrade, or exclude',
    )
    .option('--resolved-labels-json <json>', 'The labels, for resolve')
    .option('--resolved-labels-file <path>', 'The labels, for resolve')
    .option('--rationale <text>')
    .action(async function (this: Command, queueId: string, recordId: string) {
      const options = getRuntimeOptions(program, runtime)
      const client = await requireClient(options, 'adjudication resolve')
      await emit(
        await client.postJson(
          `${disagreementsPath(queueId, recordId)}/resolve`,
          await resolveBody(this.opts<ResolveOptions>()),
        ),
        outputMode(options),
      )
    })
}

function disagreementsPath(queueId: string, recordId?: string): string {
  const base = `/api/v1/adjudication/queues/${encodeURIComponent(queueId)}/disagreements`
  return recordId ? `${base}/${encodeURIComponent(recordId)}` : base
}

async function resolveBody(options: ResolveOptions): Promise<JsonObject> {
  const labels = await readOptionalJsonObject(
    options.resolvedLabelsJson,
    options.resolvedLabelsFile,
  )
  return {
    ...(options.resolution ? { resolution: options.resolution } : {}),
    ...(labels ? { resolved_labels: labels } : {}),
    ...(options.rationale ? { rationale: options.rationale } : {}),
    review_event_ids: options.reviewEventIds
      .split(',')
      .map((id) => id.trim())
      .filter(Boolean),
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
