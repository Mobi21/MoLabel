import type { Command } from 'commander'

import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import { buildClient, getRuntimeOptions, outputMode, resolveWorkspaceId } from './context.js'

interface QualityQueryOptions {
  workspaceId?: string
  datasetId?: string
  taskSchemaId?: string
}

export function registerQualityCommands(program: Command, runtime: CliRuntimeOptions): void {
  const quality = program.command('quality').description('Quality operations')

  quality
    .command('dashboard')
    .description('Show the quality dashboard')
    .option('--workspace-id <id>', 'Workspace ID')
    .option('--dataset-id <id>', 'Dataset ID')
    .option('--task-schema-id <id>', 'Task schema ID')
    .action(async function (this: Command) {
      await runQualityDashboard(
        getRuntimeOptions(program, runtime),
        this.opts<QualityQueryOptions>(),
      )
    })

  quality
    .command('agreement')
    .description('Show agreement metrics')
    .option('--workspace-id <id>', 'Workspace ID')
    .option('--dataset-id <id>', 'Dataset ID')
    .option('--task-schema-id <id>', 'Task schema ID')
    .action(async function (this: Command) {
      await runQualityAgreement(
        getRuntimeOptions(program, runtime),
        this.opts<QualityQueryOptions>(),
      )
    })

  quality
    .command('drift')
    .description('Show drift metrics')
    .option('--workspace-id <id>', 'Workspace ID')
    .option('--dataset-id <id>', 'Dataset ID')
    .action(async function (this: Command) {
      await runQualityDrift(getRuntimeOptions(program, runtime), this.opts<QualityQueryOptions>())
    })
}

async function runQualityDashboard(
  options: CliRuntimeOptions,
  query: QualityQueryOptions,
): Promise<void> {
  const client = await requireBackendClient(options, 'quality dashboard')
  const workspaceId = await resolveWorkspaceId(options, query.workspaceId)
  const response = await client.getJson<Record<string, unknown>>(
    `/api/v1/quality/dashboard${buildQuery({
      workspace_id: workspaceId,
      dataset_id: query.datasetId,
      task_schema_id: query.taskSchemaId,
    })}`,
  )
  await emit(response, outputMode(options))
}

async function runQualityAgreement(
  options: CliRuntimeOptions,
  query: QualityQueryOptions,
): Promise<void> {
  const client = await requireBackendClient(options, 'quality agreement')
  const workspaceId = await resolveWorkspaceId(options, query.workspaceId)
  const response = await client.getJson<Record<string, unknown>>(
    `/api/v1/quality/agreement${buildQuery({
      workspace_id: workspaceId,
      dataset_id: query.datasetId,
      task_schema_id: query.taskSchemaId,
    })}`,
  )
  await emit(response, outputMode(options))
}

async function runQualityDrift(options: CliRuntimeOptions, query: QualityQueryOptions): Promise<void> {
  const client = await requireBackendClient(options, 'quality drift')
  const workspaceId = await resolveWorkspaceId(options, query.workspaceId)
  const response = await client.getJson<Record<string, unknown>>(
    `/api/v1/quality/drift${buildQuery({
      workspace_id: workspaceId,
      dataset_id: query.datasetId,
    })}`,
  )
  await emit(response, outputMode(options))
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
