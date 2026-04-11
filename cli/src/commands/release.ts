import { resolve } from 'node:path'

import type { Command } from 'commander'

import { readInputText } from '../artifacts/input.js'
import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import { buildClient, getRuntimeOptions, outputMode, resolveWorkspaceId } from './context.js'

interface ReleaseListOptions {
  workspaceId?: string
  status?: string
}

interface JsonBodyOptions {
  file?: string
  bodyText?: string
}

export function registerReleaseCommands(program: Command, runtime: CliRuntimeOptions): void {
  const release = program.command('release').description('Release operations')

  release
    .command('list')
    .description('List releases')
    .option('--workspace-id <id>', 'Workspace ID')
    .option('--status <status>', 'Release status filter')
    .action(async function (this: Command) {
      await runReleaseList(getRuntimeOptions(program, runtime), this.opts<ReleaseListOptions>())
    })

  release
    .command('create')
    .description('Create a release')
    .option('--file <path>', 'JSON body file')
    .option('--body-text <json>', 'JSON body text')
    .action(async function (this: Command) {
      await runReleaseCreate(getRuntimeOptions(program, runtime), this.opts<JsonBodyOptions>())
    })

  release
    .command('get <releaseId>')
    .description('Get release detail')
    .action(async (releaseId: string) => {
      await runReleaseGet(getRuntimeOptions(program, runtime), releaseId)
    })

  release
    .command('approve <releaseId>')
    .description('Approve a release')
    .option('--notes <notes>', 'Approval notes')
    .action(async function (this: Command, releaseId: string) {
      await runReleaseApprove(
        getRuntimeOptions(program, runtime),
        releaseId,
        this.opts<{ notes?: string }>(),
      )
    })
}

async function runReleaseList(options: CliRuntimeOptions, query: ReleaseListOptions): Promise<void> {
  const client = await requireBackendClient(options, 'release list')
  const workspaceId = await resolveWorkspaceId(options, query.workspaceId)
  const response = await client.getJson<Record<string, unknown>>(
    `/api/v1/releases${buildQuery({
      workspace_id: workspaceId,
      status: query.status,
    })}`,
  )
  await emit(response, outputMode(options))
}

async function runReleaseCreate(options: CliRuntimeOptions, bodyOptions: JsonBodyOptions): Promise<void> {
  const client = await requireBackendClient(options, 'release create')
  const body = await readJsonBody(bodyOptions, 'release create requires --file, --body-text, or piped stdin')
  const response = await client.postJson<Record<string, unknown>>('/api/v1/releases', body)
  await emit(response, outputMode(options))
}

async function runReleaseGet(options: CliRuntimeOptions, releaseId: string): Promise<void> {
  const client = await requireBackendClient(options, 'release get')
  const response = await client.getJson<Record<string, unknown>>(`/api/v1/releases/${releaseId}`)
  await emit(response, outputMode(options))
}

async function runReleaseApprove(
  options: CliRuntimeOptions,
  releaseId: string,
  commandOptions: { notes?: string },
): Promise<void> {
  const client = await requireBackendClient(options, 'release approve')
  const response = await client.postJson<Record<string, unknown>>(
    `/api/v1/releases/${releaseId}/approve`,
    {
      approved: true,
      notes: commandOptions.notes,
    },
  )
  await emit(response, outputMode(options))
}

async function readJsonBody(options: JsonBodyOptions, errorMessage: string): Promise<Record<string, unknown>> {
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

function buildQuery(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value && value.trim()) {
      search.set(key, value)
    }
  }
  const query = search.toString()
  return query ? `?${query}` : ''
}

async function requireBackendClient(
  options: CliRuntimeOptions,
  commandName: string,
): Promise<NonNullable<Awaited<ReturnType<typeof buildClient>>>> {
  const client = await buildClient(options)
  if (!client) {
    throw new Error(`${commandName} requires --base-url or MOLABEL_BASE_URL`)
  }
  return client
}
