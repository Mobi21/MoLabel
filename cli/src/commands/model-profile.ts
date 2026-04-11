import { resolve } from 'node:path'

import type { Command } from 'commander'

import { readInputText } from '../artifacts/input.js'
import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import { getRuntimeOptions, outputMode, requireClient } from './context.js'

interface JsonBodyOptions {
  file?: string
  bodyText?: string
}

interface ModelProfileListOptions {
  providerType?: string
}

export function registerModelProfileCommands(program: Command, runtime: CliRuntimeOptions): void {
  const modelProfile = program.command('model-profile').description('Model profile operations')

  modelProfile
    .command('list')
    .description('List model profiles')
    .option('--provider-type <type>', 'Provider type filter')
    .action(async function (this: Command) {
      await runModelProfileList(
        getRuntimeOptions(program, runtime),
        this.opts<ModelProfileListOptions>(),
      )
    })

  modelProfile
    .command('create')
    .description('Create a model profile')
    .option('--file <path>', 'JSON body file')
    .option('--body-text <json>', 'JSON body text')
    .action(async function (this: Command) {
      await runModelProfileCreate(getRuntimeOptions(program, runtime), this.opts<JsonBodyOptions>())
    })

  modelProfile
    .command('get <profileId>')
    .description('Get a model profile')
    .action(async (profileId: string) => {
      await runModelProfileGet(getRuntimeOptions(program, runtime), profileId)
    })

  modelProfile
    .command('update <profileId>')
    .description('Update a model profile')
    .option('--file <path>', 'JSON body file')
    .option('--body-text <json>', 'JSON body text')
    .action(async function (this: Command, profileId: string) {
      await runModelProfileUpdate(
        getRuntimeOptions(program, runtime),
        profileId,
        this.opts<JsonBodyOptions>(),
      )
    })

  modelProfile
    .command('delete <profileId>')
    .description('Delete a model profile')
    .action(async (profileId: string) => {
      await runModelProfileDelete(getRuntimeOptions(program, runtime), profileId)
    })

  modelProfile
    .command('test <profileId>')
    .description('Test model profile connectivity')
    .action(async (profileId: string) => {
      await runModelProfileTest(getRuntimeOptions(program, runtime), profileId)
    })
}

async function runModelProfileList(
  options: CliRuntimeOptions,
  query: ModelProfileListOptions,
): Promise<void> {
  const client = await requireClient(options)
  const search = new URLSearchParams()
  if (query.providerType?.trim()) {
    search.set('provider_type', query.providerType.trim())
  }
  const suffix = search.size > 0 ? `?${search.toString()}` : ''
  const response = await client.getJson<Record<string, unknown>[]>(
    `/api/v1/model-profiles${suffix}`,
  )
  await emit(response, outputMode(options))
}

async function runModelProfileCreate(
  options: CliRuntimeOptions,
  bodyOptions: JsonBodyOptions,
): Promise<void> {
  const client = await requireClient(options)
  const body = await readJsonBody(
    bodyOptions,
    'model-profile create requires --file, --body-text, or piped stdin',
  )
  const response = await client.postJson<Record<string, unknown>>('/api/v1/model-profiles', body)
  await emit(response, outputMode(options))
}

async function runModelProfileGet(options: CliRuntimeOptions, profileId: string): Promise<void> {
  const client = await requireClient(options)
  const response = await client.getJson<Record<string, unknown>>(`/api/v1/model-profiles/${profileId}`)
  await emit(response, outputMode(options))
}

async function runModelProfileUpdate(
  options: CliRuntimeOptions,
  profileId: string,
  bodyOptions: JsonBodyOptions,
): Promise<void> {
  const client = await requireClient(options)
  const body = await readJsonBody(
    bodyOptions,
    'model-profile update requires --file, --body-text, or piped stdin',
  )
  const response = await client.patchJson<Record<string, unknown>>(
    `/api/v1/model-profiles/${profileId}`,
    body,
  )
  await emit(response, outputMode(options))
}

async function runModelProfileDelete(
  options: CliRuntimeOptions,
  profileId: string,
): Promise<void> {
  const client = await requireClient(options)
  await client.delete(`/api/v1/model-profiles/${profileId}`)
  await emit({ ok: true, deleted: profileId }, outputMode(options))
}

async function runModelProfileTest(options: CliRuntimeOptions, profileId: string): Promise<void> {
  const client = await requireClient(options)
  const response = await client.postJson<Record<string, unknown>>(
    `/api/v1/model-profiles/${profileId}/test`,
    {},
  )
  await emit(response, outputMode(options))
}

async function readJsonBody(
  options: JsonBodyOptions,
  errorMessage: string,
): Promise<Record<string, unknown>> {
  const raw = await readInputText({
    file: options.file ? resolve(options.file) : undefined,
    text: options.bodyText,
    allowStdin: true,
    errorMessage,
  })

  const parsed = JSON.parse(raw) as unknown
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('JSON body must be an object')
  }
  return parsed as Record<string, unknown>
}
