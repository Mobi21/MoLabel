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

interface JsonBodyOptions {
  file?: string
  bodyText?: string
}

interface AgentRunListOptions {
  workspaceId?: string
  datasetId?: string
  status?: string
  agentRole?: string
  modelProfileId?: string
  comparisonId?: string
}

interface AgentRunOutputsOptions {
  normalizationStatus?: string
}

export function registerAgentRunCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const agentRun = program
    .command('agent-run')
    .description('Agent run operations')

  agentRun
    .command('list')
    .description('List agent runs')
    .option('--workspace-id <id>', 'Workspace ID')
    .option('--dataset-id <id>', 'Dataset ID')
    .option('--status <status>', 'Run status filter')
    .option('--agent-role <role>', 'Agent role filter')
    .option('--model-profile-id <id>', 'Model profile filter')
    .option('--comparison-id <id>', 'Comparison ID filter')
    .action(async function (this: Command) {
      await runAgentRunList(
        getRuntimeOptions(program, runtime),
        this.opts<AgentRunListOptions>(),
      )
    })

  agentRun
    .command('get <agentRunId>')
    .description('Get an agent run')
    .action(async (agentRunId: string) => {
      await runAgentRunGet(getRuntimeOptions(program, runtime), agentRunId)
    })

  agentRun
    .command('inspect <agentRunId>')
    .description('Inspect an agent run')
    .action(async (agentRunId: string) => {
      await runAgentRunGet(getRuntimeOptions(program, runtime), agentRunId)
    })

  agentRun
    .command('start')
    .description('Start an agent run')
    .option('--file <path>', 'JSON body file')
    .option('--body-text <json>', 'JSON body text')
    .action(async function (this: Command) {
      await runAgentRunStart(
        getRuntimeOptions(program, runtime),
        this.opts<JsonBodyOptions>(),
      )
    })

  agentRun
    .command('compare')
    .description('Start a comparison run')
    .option('--file <path>', 'JSON body file')
    .option('--body-text <json>', 'JSON body text')
    .action(async function (this: Command) {
      await runAgentRunCompare(
        getRuntimeOptions(program, runtime),
        this.opts<JsonBodyOptions>(),
      )
    })

  agentRun
    .command('cancel <agentRunId>')
    .description('Cancel an agent run')
    .action(async (agentRunId: string) => {
      await runAgentRunCancel(getRuntimeOptions(program, runtime), agentRunId)
    })

  agentRun
    .command('outputs <agentRunId>')
    .description('List outputs for an agent run')
    .option('--normalization-status <status>', 'Normalization status filter')
    .action(async function (this: Command, agentRunId: string) {
      await runAgentRunOutputs(
        getRuntimeOptions(program, runtime),
        agentRunId,
        this.opts<AgentRunOutputsOptions>(),
      )
    })

  agentRun
    .command('output <agentRunId> <recordId>')
    .description('Get a specific output for a record')
    .action(async (agentRunId: string, recordId: string) => {
      await runAgentRunOutput(
        getRuntimeOptions(program, runtime),
        agentRunId,
        recordId,
      )
    })

  agentRun
    .command('analytics')
    .description('Show agent analytics')
    .option('--workspace-id <id>', 'Workspace ID')
    .option('--dataset-id <id>', 'Dataset ID')
    .option('--model-profile-id <id>', 'Model profile ID')
    .option('--agent-role <role>', 'Agent role filter')
    .action(async function (this: Command) {
      await runAgentRunAnalytics(
        getRuntimeOptions(program, runtime),
        this.opts<AgentRunListOptions>(),
      )
    })
}

async function runAgentRunList(
  options: CliRuntimeOptions,
  query: AgentRunListOptions,
): Promise<void> {
  const client = await requireBackendClient(options, 'agent-run list')
  const workspaceId = await resolveWorkspaceId(options, query.workspaceId)
  const response = await client.getJson(
    `/api/v1/agent-runs${buildQuery({
      workspace_id: workspaceId,
      dataset_id: query.datasetId,
      status: query.status,
      agent_role: query.agentRole,
      model_profile_id: query.modelProfileId,
      comparison_id: query.comparisonId,
    })}`,
  )
  await emit(response, outputMode(options))
}

async function runAgentRunGet(
  options: CliRuntimeOptions,
  agentRunId: string,
): Promise<void> {
  const client = await requireBackendClient(options, 'agent-run get')
  const response = await client.getJson(`/api/v1/agent-runs/${agentRunId}`)
  await emit(response, outputMode(options))
}

async function runAgentRunStart(
  options: CliRuntimeOptions,
  bodyOptions: JsonBodyOptions,
): Promise<void> {
  const client = await requireBackendClient(options, 'agent-run start')
  const body = await readJsonBody(
    bodyOptions,
    'agent-run start requires --file, --body-text, or piped stdin',
  )
  const response = await client.postJson('/api/v1/agent-runs', body)
  await emit(response, outputMode(options))
}

async function runAgentRunCompare(
  options: CliRuntimeOptions,
  bodyOptions: JsonBodyOptions,
): Promise<void> {
  const client = await requireBackendClient(options, 'agent-run compare')
  const body = await readJsonBody(
    bodyOptions,
    'agent-run compare requires --file, --body-text, or piped stdin',
  )
  const response = await client.postJson('/api/v1/agent-runs/compare', body)
  await emit(response, outputMode(options))
}

async function runAgentRunCancel(
  options: CliRuntimeOptions,
  agentRunId: string,
): Promise<void> {
  const client = await requireBackendClient(options, 'agent-run cancel')
  const response = await client.postJson(
    `/api/v1/agent-runs/${agentRunId}/cancel`,
    {},
  )
  await emit(response, outputMode(options))
}

async function runAgentRunOutputs(
  options: CliRuntimeOptions,
  agentRunId: string,
  query: AgentRunOutputsOptions,
): Promise<void> {
  const client = await requireBackendClient(options, 'agent-run outputs')
  const response = await client.getJson(
    `/api/v1/agent-runs/${agentRunId}/outputs${buildQuery({
      normalization_status: query.normalizationStatus,
    })}`,
  )
  await emit(response, outputMode(options))
}

async function runAgentRunOutput(
  options: CliRuntimeOptions,
  agentRunId: string,
  recordId: string,
): Promise<void> {
  const client = await requireBackendClient(options, 'agent-run output')
  const response = await client.getJson(
    `/api/v1/agent-runs/${agentRunId}/outputs/${recordId}`,
  )
  await emit(response, outputMode(options))
}

async function runAgentRunAnalytics(
  options: CliRuntimeOptions,
  query: AgentRunListOptions,
): Promise<void> {
  const client = await requireBackendClient(options, 'agent-run analytics')
  const workspaceId = await resolveWorkspaceId(options, query.workspaceId)
  const response = await client.getJson(
    `/api/v1/agent-runs/analytics${buildQuery({
      workspace_id: workspaceId,
      dataset_id: query.datasetId,
      model_profile_id: query.modelProfileId,
      agent_role: query.agentRole,
    })}`,
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
