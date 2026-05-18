import { extname, resolve } from 'node:path'

import type { Command } from 'commander'
import { parse as parseYaml } from 'yaml'

import { readInputText } from '../artifacts/input.js'
import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import {
  detectWorkspaceRoot,
  getRuntimeOptions,
  listLocalVersionedArtifacts,
  outputMode,
  readJsonInput,
  requireClient,
  resolveWorkspaceId,
  resolveWorkflowRemote,
  safeGetJson,
} from './context.js'

export function registerWorkflowCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const workflow = program
    .command('workflow')
    .description('Workflow operations')
  workflow
    .command('list')
    .description('List workflows')
    .action(async () => {
      await runWorkflowList(getRuntimeOptions(program, runtime))
    })
  registerWorkflowCreateCommand(workflow, program, runtime, 'create')
  registerWorkflowCreateCommand(workflow, program, runtime, 'new')
  workflow
    .command('run <selector>')
    .description('Execute a workflow by slug, id, or file selector')
    .action(async (selector: string) => {
      await runWorkflowRun(getRuntimeOptions(program, runtime), selector)
    })
  workflow
    .command('executions <selector>')
    .description('List executions for a workflow')
    .action(async (selector: string) => {
      await runWorkflowExecutions(getRuntimeOptions(program, runtime), selector)
    })
  workflow
    .command('execution <selector> <execution-id>')
    .description('Get workflow execution detail')
    .action(async (selector: string, executionId: string) => {
      await runWorkflowExecution(
        getRuntimeOptions(program, runtime),
        selector,
        executionId,
      )
    })
  workflow
    .command('advance <selector> <execution-id> <step-id>')
    .description('Advance a paused workflow step')
    .action(async (selector: string, executionId: string, stepId: string) => {
      await runWorkflowAdvance(
        getRuntimeOptions(program, runtime),
        selector,
        executionId,
        stepId,
      )
    })
  workflow
    .command('pause <selector> <execution-id>')
    .description('Pause a workflow execution')
    .action(async (selector: string, executionId: string) => {
      await runWorkflowPause(
        getRuntimeOptions(program, runtime),
        selector,
        executionId,
      )
    })
  workflow
    .command('cancel <selector> <execution-id>')
    .description('Cancel a workflow execution')
    .action(async (selector: string, executionId: string) => {
      await runWorkflowCancel(
        getRuntimeOptions(program, runtime),
        selector,
        executionId,
      )
    })
  workflow
    .command('templates')
    .description('Show built-in workflow templates')
    .action(async () => {
      await runWorkflowTemplates(getRuntimeOptions(program, runtime))
    })
}

function registerWorkflowCreateCommand(
  workflow: Command,
  program: Command,
  runtime: CliRuntimeOptions,
  name: 'create' | 'new',
): void {
  workflow
    .command(name)
    .description(
      name === 'new'
        ? 'Create a workflow from a built-in template, JSON, or YAML'
        : 'Create a workflow definition from JSON, YAML, or a built-in template',
    )
    .option('--file <path>', 'Workflow definition file (JSON or YAML)')
    .option('--template <templateId>', 'Built-in workflow template ID')
    .option('--workspace-id <id>', 'Workspace ID override')
    .option('--name <name>')
    .option('--slug <slug>')
    .option('--description <text>')
    .option('--file-path <path>')
    .action(async function (this: Command) {
      const commandOptions = this.opts<{
        file?: string
        template?: string
        workspaceId?: string
        name?: string
        slug?: string
        description?: string
        filePath?: string
      }>()
      await runWorkflowCreate(
        getRuntimeOptions(program, runtime),
        commandOptions,
      )
    })
}

async function runWorkflowList(options: CliRuntimeOptions): Promise<void> {
  const client = await safeClient(options)
  if (client) {
    const response = await client.getJson<{ items?: unknown[] }>(
      '/api/v1/workflows',
    )
    await emit(response, outputMode(options))
    return
  }

  const workspace = await detectWorkspaceRoot(options.workspaceRoot)
  if (!workspace.rootDir) {
    await emit({ items: [] }, outputMode(options))
    return
  }

  const workflows = await listLocalVersionedArtifacts(
    workspace.rootDir,
    'workbench/workflows',
  )
  await emit({ items: workflows }, outputMode(options))
}

async function runWorkflowCreate(
  options: CliRuntimeOptions,
  commandOptions: {
    file?: string
    template?: string
    workspaceId?: string
    name?: string
    slug?: string
    description?: string
    filePath?: string
  },
): Promise<void> {
  const client = await requireClient(options)
  if (commandOptions.file && commandOptions.template) {
    throw new Error(
      'workflow create accepts either --file or --template, not both',
    )
  }

  const workspaceId = await resolveWorkspaceId(
    options,
    commandOptions.workspaceId,
  )
  const body = commandOptions.file
    ? await readWorkflowDefinitionFile(commandOptions.file, workspaceId)
    : commandOptions.template
      ? await readWorkflowTemplateDefinition(
          client,
          commandOptions.template,
          workspaceId,
          compactWorkflowOverrides({
            name: commandOptions.name,
            slug: commandOptions.slug,
            description: commandOptions.description,
            filePath: commandOptions.filePath,
          }),
        )
      : {
          workspace_id: workspaceId,
          name: commandOptions.name,
          workflow_slug: commandOptions.slug,
          description: commandOptions.description,
          file_path: commandOptions.filePath,
          steps: [],
          edges: [],
        }

  if (!body.name) {
    throw new Error('workflow create requires name')
  }

  const response = await client.postJson('/api/v1/workflows', body)
  await emit(response, outputMode(options))
}

async function runWorkflowRun(
  options: CliRuntimeOptions,
  selector: string,
): Promise<void> {
  const client = await requireClient(options)
  const workflow = await resolveWorkflowRemote(client, selector)
  const execution = await client.postJson(
    `/api/v1/workflows/${workflow.workflow_id}/execute`,
    {},
  )
  await emit(execution, outputMode(options))
}

async function runWorkflowExecutions(
  options: CliRuntimeOptions,
  selector: string,
): Promise<void> {
  const client = await requireClient(options)
  const workflow = await resolveWorkflowRemote(client, selector)
  const executions = await client.getJson(
    `/api/v1/workflows/${workflow.workflow_id}/executions`,
  )
  await emit(executions, outputMode(options))
}

async function runWorkflowExecution(
  options: CliRuntimeOptions,
  selector: string,
  executionId: string,
): Promise<void> {
  const client = await requireClient(options)
  const workflow = await resolveWorkflowRemote(client, selector)
  const execution = await client.getJson(
    `/api/v1/workflows/${workflow.workflow_id}/executions/${executionId}`,
  )
  await emit(execution, outputMode(options))
}

async function runWorkflowAdvance(
  options: CliRuntimeOptions,
  selector: string,
  executionId: string,
  stepId: string,
): Promise<void> {
  const client = await requireClient(options)
  const workflow = await resolveWorkflowRemote(client, selector)
  const execution = await client.postJson(
    `/api/v1/workflows/${workflow.workflow_id}/executions/${executionId}/steps/${stepId}/advance`,
    {},
  )
  await emit(execution, outputMode(options))
}

async function runWorkflowPause(
  options: CliRuntimeOptions,
  selector: string,
  executionId: string,
): Promise<void> {
  const client = await requireClient(options)
  const workflow = await resolveWorkflowRemote(client, selector)
  const execution = await client.postJson(
    `/api/v1/workflows/${workflow.workflow_id}/executions/${executionId}/pause`,
    {},
  )
  await emit(execution, outputMode(options))
}

async function runWorkflowCancel(
  options: CliRuntimeOptions,
  selector: string,
  executionId: string,
): Promise<void> {
  const client = await requireClient(options)
  const workflow = await resolveWorkflowRemote(client, selector)
  const execution = await client.postJson(
    `/api/v1/workflows/${workflow.workflow_id}/executions/${executionId}/cancel`,
    {},
  )
  await emit(execution, outputMode(options))
}

async function runWorkflowTemplates(options: CliRuntimeOptions): Promise<void> {
  const client = await safeClient(options)
  if (client) {
    const templates = await safeGetJson<Record<string, unknown>[]>(
      client,
      '/api/v1/cli/workflow-templates',
    )
    if (templates) {
      await emit(templates, outputMode(options))
      return
    }
  }

  const templates = await import('../manifest/workflow-templates.js').then(
    ({ WORKFLOW_TEMPLATES }) => WORKFLOW_TEMPLATES.templates,
  )
  await emit(templates, outputMode(options))
}

async function safeClient(options: CliRuntimeOptions) {
  try {
    return await requireClient(options)
  } catch {
    return null
  }
}

async function readWorkflowDefinitionFile(
  path: string,
  workspaceId: string,
): Promise<Record<string, unknown>> {
  const raw = await readInputText({
    file: resolve(path),
    text: undefined,
    allowStdin: false,
    errorMessage: `Unable to read workflow file: ${path}`,
  })

  const parsed =
    extname(path).toLowerCase() === '.yaml' ||
    extname(path).toLowerCase() === '.yml'
      ? (parseYaml(raw) as Record<string, unknown> | null)
      : ((await readJsonInput({
          text: raw,
          errorMessage: `Invalid workflow JSON in ${path}`,
        })) as Record<string, unknown>)

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`Workflow file must contain an object: ${path}`)
  }

  return buildWorkflowCreateBody(parsed, {
    workspaceId,
    ...compactWorkflowOverrides({
      filePath: readString(parsed.file_path),
    }),
  })
}

async function readWorkflowTemplateDefinition(
  client: Awaited<ReturnType<typeof requireClient>>,
  templateId: string,
  workspaceId: string,
  overrides: {
    name?: string
    slug?: string
    description?: string
    filePath?: string
  },
): Promise<Record<string, unknown>> {
  const template = await client.getJson<{ yaml?: unknown }>(
    `/api/v1/cli/workflow-templates/${templateId}`,
  )
  const yaml = readString(template.yaml)
  if (!yaml) {
    throw new Error(`Workflow template '${templateId}' did not return YAML`)
  }
  const parsed = parseYaml(yaml) as Record<string, unknown> | null
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`Workflow template '${templateId}' is not a valid object`)
  }

  return buildWorkflowCreateBody(parsed, {
    workspaceId,
    ...compactWorkflowOverrides({
      name: overrides.name,
      slug: overrides.slug,
      description: overrides.description,
    }),
    filePath:
      overrides.filePath ??
      `workbench/workflows/${templateId.replace(/_/g, '-')}.yaml`,
  })
}

function compactWorkflowOverrides(
  overrides: Partial<
    Record<'name' | 'slug' | 'description' | 'filePath', string | undefined>
  >,
): {
  name?: string
  slug?: string
  description?: string
  filePath?: string
} {
  return Object.fromEntries(
    Object.entries(overrides).filter(([, value]) => value !== undefined),
  ) as {
    name?: string
    slug?: string
    description?: string
    filePath?: string
  }
}

function buildWorkflowCreateBody(
  parsed: Record<string, unknown>,
  overrides: {
    workspaceId: string
    name?: string
    slug?: string
    description?: string
    filePath?: string
  },
): Record<string, unknown> {
  const steps = Array.isArray(parsed.steps)
    ? parsed.steps.map((step, index) => normalizeWorkflowStep(step, index))
    : []
  const edges = Array.isArray(parsed.edges)
    ? parsed.edges.map((edge) => normalizeWorkflowEdge(edge))
    : []

  return {
    workspace_id: overrides.workspaceId,
    name: overrides.name ?? readString(parsed.name) ?? 'Workflow',
    workflow_slug:
      overrides.slug ??
      readString(parsed.workflow_slug) ??
      readString(parsed.slug),
    description: overrides.description ?? readString(parsed.description),
    file_path: overrides.filePath ?? readString(parsed.file_path),
    steps,
    edges,
  }
}

function normalizeWorkflowStep(
  step: unknown,
  index: number,
): Record<string, unknown> {
  if (!step || typeof step !== 'object' || Array.isArray(step)) {
    throw new Error(`Workflow step ${String(index + 1)} must be an object`)
  }
  const value = step as Record<string, unknown>
  const stepId = readString(value.step_id) ?? readString(value.id)
  const stepType = readString(value.step_type) ?? readString(value.type)
  if (!stepId || !stepType) {
    throw new Error(`Workflow step ${String(index + 1)} requires id/type`)
  }
  return {
    step_id: stepId,
    step_type: stepType,
    label: readString(value.label),
    config:
      value.config &&
      typeof value.config === 'object' &&
      !Array.isArray(value.config)
        ? value.config
        : {},
    position:
      value.position &&
      typeof value.position === 'object' &&
      !Array.isArray(value.position)
        ? value.position
        : undefined,
  }
}

function normalizeWorkflowEdge(edge: unknown): Record<string, unknown> {
  if (!edge || typeof edge !== 'object' || Array.isArray(edge)) {
    throw new Error('Workflow edge must be an object')
  }
  const value = edge as Record<string, unknown>
  const source = readString(value.source_step_id) ?? readString(value.source)
  const target = readString(value.target_step_id) ?? readString(value.target)
  if (!source || !target) {
    throw new Error('Workflow edge requires source and target')
  }
  return {
    source_step_id: source,
    target_step_id: target,
    condition: readString(value.condition),
  }
}

function readString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined
}
