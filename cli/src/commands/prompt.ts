import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import type { Command } from 'commander'
import { parse as parseYaml } from 'yaml'

import { emit } from '../output.js'
import { readInputText } from '../artifacts/input.js'
import type { CliRuntimeOptions } from '../types.js'
import {
  buildClient,
  detectWorkspaceRoot,
  getRuntimeOptions,
  outputMode,
} from './context.js'

type JsonObject = Record<string, unknown>

export function registerPromptCommands(program: Command, runtime: CliRuntimeOptions): void {
  const prompt = program.command('prompt').description('Prompt operations')

  prompt
    .command('list')
    .description('List prompts')
    .option('--workspace-id <id>', 'Workspace ID override')
    .option('--agent-role <role>')
    .option('--task-schema-id <id>')
    .action(async function (this: Command) {
      const commandOptions = this.opts<{
        agentRole?: string
        taskSchemaId?: string
        workspaceId?: string
      }>()
      await runPromptList(getRuntimeOptions(program, runtime), commandOptions)
    })

  prompt
    .command('get <prompt-id>')
    .description('Get a prompt')
    .action(async (promptId: string) => {
      await runPromptGet(getRuntimeOptions(program, runtime), promptId)
    })

  prompt
    .command('create')
    .description('Create a prompt')
    .option('--file <path>', 'JSON file with the request body')
    .option('--workspace-id <id>', 'Workspace ID override')
    .option('--name <name>')
    .option('--agent-role <role>')
    .option('--task-schema-id <id>')
    .option('--system-instructions <text>')
    .option('--task-rubric <text>')
    .option('--few-shot-json <json>')
    .option('--file-path <path>')
    .action(async function (this: Command) {
      const commandOptions = this.opts<{
        agentRole?: string
        file?: string
        filePath?: string
        fewShotJson?: string
        name?: string
        systemInstructions?: string
        taskRubric?: string
        taskSchemaId?: string
        workspaceId?: string
      }>()
      await runPromptCreate(getRuntimeOptions(program, runtime), commandOptions)
    })

  prompt
    .command('diff <prompt-id>')
    .description('Diff two prompt versions')
    .option('--v1 <version>', 'First version', 'v1')
    .option('--v2 <version>', 'Second version', 'v2')
    .action(async function (this: Command, promptId: string) {
      const commandOptions = this.opts<{ v1?: string; v2?: string }>()
      await runPromptDiff(
        getRuntimeOptions(program, runtime),
        promptId,
        commandOptions.v1 ?? 'v1',
        commandOptions.v2 ?? 'v2',
      )
    })
}

async function runPromptList(
  options: CliRuntimeOptions,
  commandOptions: { agentRole?: string; taskSchemaId?: string; workspaceId?: string },
): Promise<void> {
  const client = await requireClient(options, 'prompt list')
  const workspaceId = await resolveWorkspaceId(options, commandOptions.workspaceId)
  const params = new URLSearchParams({ workspace_id: workspaceId })
  if (commandOptions.agentRole) {
    params.set('agent_role', commandOptions.agentRole)
  }
  if (commandOptions.taskSchemaId) {
    params.set('task_schema_id', commandOptions.taskSchemaId)
  }
  const response = await client.getJson(`/api/v1/prompts?${params.toString()}`)
  await emit(response, outputMode(options))
}

async function runPromptGet(options: CliRuntimeOptions, promptId: string): Promise<void> {
  const client = await requireClient(options, 'prompt get')
  const response = await client.getJson(`/api/v1/prompts/${promptId}`)
  await emit(response, outputMode(options))
}

async function runPromptCreate(
  options: CliRuntimeOptions,
  commandOptions: {
    agentRole?: string
    file?: string
    filePath?: string
    fewShotJson?: string
    name?: string
    systemInstructions?: string
    taskRubric?: string
    taskSchemaId?: string
    workspaceId?: string
  },
): Promise<void> {
  const client = await requireClient(options, 'prompt create')
  let body: JsonObject
  if (commandOptions.file) {
    body = await readJsonFile<JsonObject>(commandOptions.file)
  } else {
    body = {
      workspace_id: await resolveWorkspaceId(options, commandOptions.workspaceId),
      name: commandOptions.name,
      agent_role: commandOptions.agentRole,
      task_schema_id: commandOptions.taskSchemaId,
      system_instructions: commandOptions.systemInstructions,
      task_rubric: commandOptions.taskRubric,
      few_shot_examples: parseJsonOption(commandOptions.fewShotJson, 'few-shot-json'),
      file_path: commandOptions.filePath,
    }
  }

  if (!commandOptions.file) {
    requireField(body, 'name', 'prompt create')
    requireField(body, 'agent_role', 'prompt create')
    requireField(body, 'task_schema_id', 'prompt create')
    requireField(body, 'system_instructions', 'prompt create')
    if (!body.workspace_id) {
      body.workspace_id = await resolveWorkspaceId(options, commandOptions.workspaceId)
    }
  } else if (!body.workspace_id) {
    body.workspace_id = await resolveWorkspaceId(options, commandOptions.workspaceId)
  }

  const response = await client.postJson('/api/v1/prompts', body)
  await emit(response, outputMode(options))
}

async function runPromptDiff(
  options: CliRuntimeOptions,
  promptId: string,
  v1: string,
  v2: string,
): Promise<void> {
  const client = await requireClient(options, 'prompt diff')
  const path = `/api/v1/prompts/${promptId}/diff?v1=${encodeURIComponent(v1)}&v2=${encodeURIComponent(v2)}`
  const response = await client.getJson(path)
  await emit(response, outputMode(options))
}

async function resolveWorkspaceId(
  options: CliRuntimeOptions,
  explicitWorkspaceId?: string,
): Promise<string> {
  if (explicitWorkspaceId) {
    return explicitWorkspaceId
  }

  const workspace = await detectWorkspaceRoot(options.workspaceRoot)
  if (!workspace.manifestPath) {
    throw new Error('workspace_id is required when no workspace manifest is available')
  }

  const manifest = await readFile(workspace.manifestPath, 'utf8')
  const parsed = parseYaml(manifest) as { workspace_id?: string } | null
  const workspaceId = parsed?.workspace_id
  if (!workspaceId) {
    throw new Error('workspace_id is required; pass --workspace-id or bootstrap a workspace')
  }
  return String(workspaceId)
}

async function readJsonFile<T extends JsonObject>(path: string): Promise<T> {
  const raw = await readInputText({
    file: resolve(path),
    text: undefined,
    errorMessage: `Unable to read JSON file: ${path}`,
  })
  try {
    return JSON.parse(raw) as T
  } catch (error) {
    throw new Error(`Invalid JSON in ${path}: ${(error as Error).message}`)
  }
}

function parseJsonOption<T>(value: string | undefined, flagName: string): T | undefined {
  if (!value) {
    return undefined
  }
  try {
    return JSON.parse(value) as T
  } catch (error) {
    throw new Error(`Invalid JSON for --${flagName}: ${(error as Error).message}`)
  }
}

function requireField(body: JsonObject, key: string, commandName: string): void {
  if (!(key in body) || body[key] === undefined || body[key] === null || body[key] === '') {
    throw new Error(`${commandName} requires ${key}`)
  }
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
