import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import type { Command } from 'commander'

import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import { buildClient, getRuntimeOptions, outputMode } from './context.js'

type JsonObject = Record<string, unknown>

export function registerReviewCommands(program: Command, runtime: CliRuntimeOptions): void {
  const review = program.command('review').description('Review operations')

  review
    .command('submit <task-id>')
    .description('Submit a review for a claimed task')
    .option('--labels-json <json>')
    .option('--labels-file <path>')
    .option('--decision <decision>')
    .option('--rationale <text>')
    .option('--no-auto-claim-next')
    .action(async function (this: Command, taskId: string) {
      const options = this.opts<{
        labelsJson?: string
        labelsFile?: string
        decision?: string
        rationale?: string
        autoClaimNext?: boolean
      }>()
      await runReviewSubmit(
        getRuntimeOptions(program, runtime),
        taskId,
        options.labelsJson,
        options.labelsFile,
        options.decision,
        options.rationale,
        options.autoClaimNext,
      )
    })

  review
    .command('skip <task-id>')
    .description('Skip a claimed task and claim the next available item')
    .action(async (taskId: string) => {
      await runReviewSkip(getRuntimeOptions(program, runtime), taskId)
    })

  review
    .command('release <task-id>')
    .description('Release a claim back to the available pool')
    .action(async (taskId: string) => {
      await runReviewRelease(getRuntimeOptions(program, runtime), taskId)
    })

  review
    .command('draft <task-id>')
    .description('Save draft labels for a claimed task')
    .option('--labels-json <json>')
    .option('--labels-file <path>')
    .action(async function (this: Command, taskId: string) {
      const options = this.opts<{
        labelsJson?: string
        labelsFile?: string
      }>()
      await runReviewDraft(
        getRuntimeOptions(program, runtime),
        taskId,
        options.labelsJson,
        options.labelsFile,
      )
    })

  review
    .command('reveal-ai <task-id>')
    .description('Reveal the attached agent output for a claimed task')
    .action(async (taskId: string) => {
      await runReviewRevealAi(getRuntimeOptions(program, runtime), taskId)
    })

  review
    .command('correct <task-id>')
    .description('Submit a correction for a previously reviewed task')
    .option('--labels-json <json>')
    .option('--labels-file <path>')
    .option('--decision <decision>')
    .option('--rationale <text>')
    .action(async function (this: Command, taskId: string) {
      const options = this.opts<{
        labelsJson?: string
        labelsFile?: string
        decision?: string
        rationale?: string
      }>()
      await runReviewCorrect(
        getRuntimeOptions(program, runtime),
        taskId,
        options.labelsJson,
        options.labelsFile,
        options.decision,
        options.rationale,
      )
    })
}

async function runReviewSubmit(
  options: CliRuntimeOptions,
  taskId: string,
  labelsJson?: string,
  labelsFile?: string,
  decision?: string,
  rationale?: string,
  autoClaimNext?: boolean,
): Promise<void> {
  const client = await requireClient(options, 'review submit')
  const response = await client.postJson<Record<string, unknown>>(
    `/api/v1/review-tasks/${encodeURIComponent(taskId)}/submit`,
    {
      labels: await readLabelsPayload(labelsJson, labelsFile),
      decision: decision ?? null,
      rationale: rationale ?? null,
      auto_claim_next: autoClaimNext ?? true,
    },
  )
  await emit(response, outputMode(options))
}

async function runReviewSkip(options: CliRuntimeOptions, taskId: string): Promise<void> {
  const client = await requireClient(options, 'review skip')
  const response = await client.postJson<Record<string, unknown>>(
    `/api/v1/review-tasks/${encodeURIComponent(taskId)}/skip`,
    {},
  )
  await emit(response, outputMode(options))
}

async function runReviewRelease(options: CliRuntimeOptions, taskId: string): Promise<void> {
  const client = await requireClient(options, 'review release')
  const response = await client.postJson<Record<string, unknown>>(
    `/api/v1/review-tasks/${encodeURIComponent(taskId)}/release`,
    {},
  )
  await emit(response, outputMode(options))
}

async function runReviewDraft(
  options: CliRuntimeOptions,
  taskId: string,
  labelsJson?: string,
  labelsFile?: string,
): Promise<void> {
  const client = await requireClient(options, 'review draft')
  const response = await client.postJson<Record<string, unknown>>(
    `/api/v1/review-tasks/${encodeURIComponent(taskId)}/draft`,
    {
      draft_labels: await readLabelsPayload(labelsJson, labelsFile),
    },
  )
  await emit(response, outputMode(options))
}

async function runReviewRevealAi(
  options: CliRuntimeOptions,
  taskId: string,
): Promise<void> {
  const client = await requireClient(options, 'review reveal-ai')
  const response = await client.postJson<Record<string, unknown>>(
    `/api/v1/review-tasks/${encodeURIComponent(taskId)}/reveal-ai`,
    {},
  )
  await emit(response, outputMode(options))
}

async function runReviewCorrect(
  options: CliRuntimeOptions,
  taskId: string,
  labelsJson?: string,
  labelsFile?: string,
  decision?: string,
  rationale?: string,
): Promise<void> {
  const client = await requireClient(options, 'review correct')
  const response = await client.postJson<Record<string, unknown>>(
    `/api/v1/review-tasks/${encodeURIComponent(taskId)}/correct`,
    {
      labels: await readLabelsPayload(labelsJson, labelsFile),
      decision: decision ?? null,
      rationale: rationale ?? null,
    },
  )
  await emit(response, outputMode(options))
}

async function readLabelsPayload(
  labelsJson?: string,
  labelsFile?: string,
): Promise<JsonObject> {
  if (labelsFile) {
    return readJsonObjectFromText(await readFile(resolve(labelsFile), 'utf8'))
  }
  if (labelsJson) {
    return readJsonObjectFromText(labelsJson)
  }
  return {}
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
