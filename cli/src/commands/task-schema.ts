import { readFile } from 'node:fs/promises'
import { extname, resolve } from 'node:path'

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

export function registerTaskSchemaCommands(program: Command, runtime: CliRuntimeOptions): void {
  const taskSchema = program.command('task-schema').description('Task schema operations')

  taskSchema
    .command('list')
    .description('List task schemas')
    .action(async () => {
      await runTaskSchemaList(getRuntimeOptions(program, runtime))
    })

  taskSchema
    .command('get <task-schema-id>')
    .description('Get a task schema')
    .action(async (taskSchemaId: string) => {
      await runTaskSchemaGet(getRuntimeOptions(program, runtime), taskSchemaId)
    })

  taskSchema
    .command('create')
    .description('Create a task schema')
    .option('--file <path>', 'JSON file with the request body')
    .option('--workspace-id <id>', 'Workspace ID override')
    .option('--slug <slug>')
    .option('--task-type <type>')
    .option('--title <title>')
    .option('--instructions <text>')
    .option('--blind-review-policy <policy>')
    .option('--label-fields-json <json>')
    .option('--required-fields-json <json>')
    .option('--optional-fields-json <json>')
    .option('--supported-agent-roles-json <json>')
    .option('--record-selector-json <json>')
    .option('--overlap-policy-json <json>')
    .option('--adjudication-policy-json <json>')
    .option('--export-mapping-json <json>')
    .option('--default-model-profile-id <id>')
    .option('--file-path <path>')
    .action(async function (this: Command) {
      const commandOptions = this.opts<{
        adjudicationPolicyJson?: string
        blindReviewPolicy?: string
        defaultModelProfileId?: string
        exportMappingJson?: string
        file?: string
        filePath?: string
        instructions?: string
        labelFieldsJson?: string
        optionalFieldsJson?: string
        overlapPolicyJson?: string
        recordSelectorJson?: string
        requiredFieldsJson?: string
        slug?: string
        supportedAgentRolesJson?: string
        taskType?: string
        title?: string
        workspaceId?: string
      }>()
      await runTaskSchemaCreate(getRuntimeOptions(program, runtime), commandOptions)
    })
}

async function runTaskSchemaList(options: CliRuntimeOptions): Promise<void> {
  const client = await requireClient(options, 'task-schema list')
  const response = await client.getJson('/api/v1/task-schemas')
  await emit(response, outputMode(options))
}

async function runTaskSchemaGet(
  options: CliRuntimeOptions,
  taskSchemaId: string,
): Promise<void> {
  const client = await requireClient(options, 'task-schema get')
  const response = await client.getJson(`/api/v1/task-schemas/${taskSchemaId}`)
  await emit(response, outputMode(options))
}

async function runTaskSchemaCreate(
  options: CliRuntimeOptions,
  commandOptions: {
    adjudicationPolicyJson?: string
    blindReviewPolicy?: string
    defaultModelProfileId?: string
    exportMappingJson?: string
    file?: string
    filePath?: string
    instructions?: string
    labelFieldsJson?: string
    optionalFieldsJson?: string
    overlapPolicyJson?: string
    recordSelectorJson?: string
    requiredFieldsJson?: string
    slug?: string
    supportedAgentRolesJson?: string
    taskType?: string
    title?: string
    workspaceId?: string
  },
): Promise<void> {
  const client = await requireClient(options, 'task-schema create')
  let body: JsonObject
  if (commandOptions.file) {
    body = await readTaskSchemaFile(options, commandOptions.file, commandOptions.workspaceId)
  } else {
    body = {
      workspace_id: await resolveWorkspaceId(options, commandOptions.workspaceId),
      task_schema_slug: commandOptions.slug,
      task_type: commandOptions.taskType,
      title: commandOptions.title,
      instructions: commandOptions.instructions,
      blind_review_policy: commandOptions.blindReviewPolicy,
      label_fields: parseJsonOption(commandOptions.labelFieldsJson, 'label-fields-json'),
      required_fields: parseJsonOption(
        commandOptions.requiredFieldsJson,
        'required-fields-json',
      ),
      optional_fields: parseJsonOption(
        commandOptions.optionalFieldsJson,
        'optional-fields-json',
      ),
      supported_agent_roles: parseJsonOption(
        commandOptions.supportedAgentRolesJson,
        'supported-agent-roles-json',
      ),
      record_selector: parseJsonOption(
        commandOptions.recordSelectorJson,
        'record-selector-json',
      ),
      overlap_policy: parseJsonOption(commandOptions.overlapPolicyJson, 'overlap-policy-json'),
      adjudication_policy: parseJsonOption(
        commandOptions.adjudicationPolicyJson,
        'adjudication-policy-json',
      ),
      export_mapping: parseJsonOption(
        commandOptions.exportMappingJson,
        'export-mapping-json',
      ),
      default_model_profile_id: commandOptions.defaultModelProfileId,
      file_path: commandOptions.filePath,
    }
  }

  if (!commandOptions.file) {
    requireField(body, 'task_type', 'task-schema create')
    requireField(body, 'title', 'task-schema create')
    if (!body.workspace_id) {
      body.workspace_id = await resolveWorkspaceId(options, commandOptions.workspaceId)
    }
  } else if (!body.workspace_id) {
    body.workspace_id = await resolveWorkspaceId(options, commandOptions.workspaceId)
  }

  const response = await client.postJson('/api/v1/task-schemas', body)
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

async function readTaskSchemaFile(
  options: CliRuntimeOptions,
  path: string,
  workspaceId?: string,
): Promise<JsonObject> {
  const lowerExt = extname(path).toLowerCase()
  if (lowerExt !== '.yaml' && lowerExt !== '.yml') {
    return readJsonFile<JsonObject>(path)
  }

  const raw = await readInputText({
    file: resolve(path),
    text: undefined,
    errorMessage: `Unable to read task schema file: ${path}`,
  })
  const parsed = parseYaml(raw) as Record<string, unknown> | null
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`Task schema file must contain an object: ${path}`)
  }

  return {
    workspace_id: await resolveWorkspaceId(options, workspaceId),
    task_schema_slug:
      readString(parsed.task_schema_slug) ??
      readString(parsed.task_slug) ??
      readString(parsed.slug),
    task_type: readString(parsed.task_type),
    title: readString(parsed.title),
    instructions: readString(parsed.instructions),
    record_selector: parsed.record_selector,
    label_fields: Array.isArray(parsed.label_fields) ? parsed.label_fields : [],
    required_fields: Array.isArray(parsed.required_fields) ? parsed.required_fields : [],
    optional_fields: Array.isArray(parsed.optional_fields) ? parsed.optional_fields : [],
    blind_review_policy: readString(parsed.blind_review_policy),
    overlap_policy: parsed.overlap_policy,
    adjudication_policy: parsed.adjudication_policy,
    supported_agent_roles: Array.isArray(parsed.supported_agent_roles)
      ? parsed.supported_agent_roles
      : [],
    default_model_profile_id: readString(parsed.default_model_profile_id),
    export_mapping: parsed.export_mapping,
    file_path: path.includes('workbench/') ? path.slice(path.indexOf('workbench/')) : undefined,
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

function readString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined
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
