import { resolve } from 'node:path'

import type { Command } from 'commander'

import { readInputText } from '../artifacts/input.js'
import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import {
  buildClient,
  getRuntimeOptions,
  outputMode,
  resolveWorkspaceId,
} from './context.js'

interface ExportListOptions {
  workspaceId?: string
  datasetId?: string
  status?: string
}

interface JsonBodyOptions {
  file?: string
  bodyText?: string
}

export function registerExportCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const exportCommand = program
    .command('export')
    .description('Export operations')

  exportCommand
    .command('list')
    .description('List exports')
    .option('--workspace-id <id>', 'Workspace ID')
    .option('--dataset-id <id>', 'Dataset ID')
    .option('--status <status>', 'Export status filter')
    .action(async function (this: Command) {
      await runExportList(
        getRuntimeOptions(program, runtime),
        this.opts<ExportListOptions>(),
      )
    })

  exportCommand
    .command('create')
    .description('Create an export')
    .option('--file <path>', 'JSON body file')
    .option('--body-text <json>', 'JSON body text')
    .action(async function (this: Command) {
      await runExportCreate(
        getRuntimeOptions(program, runtime),
        this.opts<JsonBodyOptions>(),
      )
    })

  exportCommand
    .command('preview')
    .description('Preview an export')
    .option('--file <path>', 'JSON body file')
    .option('--body-text <json>', 'JSON body text')
    .action(async function (this: Command) {
      await runExportPreview(
        getRuntimeOptions(program, runtime),
        this.opts<JsonBodyOptions>(),
      )
    })

  exportCommand
    .command('get <exportId>')
    .description('Get export detail')
    .action(async (exportId: string) => {
      await runExportGet(getRuntimeOptions(program, runtime), exportId)
    })

  exportCommand
    .command('validate <exportId>')
    .description('Validate an export')
    .action(async (exportId: string) => {
      await runExportValidate(getRuntimeOptions(program, runtime), exportId)
    })

  exportCommand
    .command('download <exportId>')
    .description('Download an export')
    .action(async (exportId: string) => {
      await runExportDownload(getRuntimeOptions(program, runtime), exportId)
    })
}

async function runExportList(
  options: CliRuntimeOptions,
  query: ExportListOptions,
): Promise<void> {
  const client = await requireBackendClient(options, 'export list')
  const workspaceId = await resolveWorkspaceId(options, query.workspaceId)
  const response = await client.getJson(
    `/api/v1/exports${buildQuery({
      workspace_id: workspaceId,
      dataset_id: query.datasetId,
      status: query.status,
    })}`,
  )
  await emit(response, outputMode(options))
}

async function runExportCreate(
  options: CliRuntimeOptions,
  bodyOptions: JsonBodyOptions,
): Promise<void> {
  const client = await requireBackendClient(options, 'export create')
  const body = await readJsonBody(
    bodyOptions,
    'export create requires --file, --body-text, or piped stdin',
  )
  const response = await client.postJson('/api/v1/exports', body)
  await emit(response, outputMode(options))
}

async function runExportPreview(
  options: CliRuntimeOptions,
  bodyOptions: JsonBodyOptions,
): Promise<void> {
  const client = await requireBackendClient(options, 'export preview')
  const body = await readJsonBody(
    bodyOptions,
    'export preview requires --file, --body-text, or piped stdin',
  )
  const response = await client.postJson('/api/v1/exports/preview', body)
  await emit(response, outputMode(options))
}

async function runExportGet(
  options: CliRuntimeOptions,
  exportId: string,
): Promise<void> {
  const client = await requireBackendClient(options, 'export get')
  const response = await client.getJson(`/api/v1/exports/${exportId}`)
  await emit(response, outputMode(options))
}

async function runExportValidate(
  options: CliRuntimeOptions,
  exportId: string,
): Promise<void> {
  const client = await requireBackendClient(options, 'export validate')
  const response = await client.postJson(
    `/api/v1/exports/${exportId}/validate`,
    {},
  )
  await emit(response, outputMode(options))
}

async function runExportDownload(
  options: CliRuntimeOptions,
  exportId: string,
): Promise<void> {
  const client = await requireBackendClient(options, 'export download')
  const response = await client.request(
    `/api/v1/exports/${exportId}/download`,
    {
      method: 'POST',
    },
  )
  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    await emit(
      (await response.json()) as Record<string, unknown>,
      outputMode(options),
    )
    return
  }
  await emit(await response.text(), outputMode(options))
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
