import { readdir } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { homedir } from 'node:os'
import { fileURLToPath } from 'node:url'

import { Command } from 'commander'
import { COMMAND_MANIFEST } from './manifest/commands.js'
import { WORKFLOW_TEMPLATES } from './manifest/workflow-templates.js'
import { ApiClient, ApiError } from './client/http.js'
import { extractSessionTokenFromSetCookie, readSetCookieHeaders } from './client/session.js'
import { atomicWriteTextFile, readTextFile, sha256 } from './artifacts/io.js'
import { readInputText } from './artifacts/input.js'
import { diffText } from './artifacts/diff.js'
import { detectWorkspace, normalizeArtifactSelector, resolveArtifact } from './workspace-context.js'
import { emit } from './output.js'
import { getDefaultConfigPath, loadConfig, resolveConfig, saveConfig } from './config.js'
import { installSkillBundle } from './skills.js'
import type { CliConfig, CliRuntimeOptions, OutputMode } from './types.js'

export interface ProgramRunResult {
  exitCode: number
}

export function createProgram(runtime: CliRuntimeOptions = {}): Command {
  const program = new Command()
  program.name('molabel')
  program.description('MoLabel agent CLI')
  program.version('0.1.0')
  program.exitOverride()

  program
    .option('--base-url <url>', 'backend base URL')
    .option('--workspace <path>', 'workspace root override')
    .option('--config <path>', 'CLI config path')
    .option('--session <token>', 'session token override')
    .option('--json', 'force JSON output')
    .option('--raw', 'emit raw output where supported')

  program.command('doctor').description('Check environment health').action(async () => {
    await runDoctor(getRuntimeOptions(program, runtime))
  })

  program.command('status').description('Show workspace and backend status').action(async () => {
    await runStatus(getRuntimeOptions(program, runtime))
  })

  program.command('manifest').description('Print the CLI manifest').option('--json').action(async () => {
    await emit(COMMAND_MANIFEST, 'json')
  })

  const session = program.command('session').description('Session operations')
  session
    .command('whoami')
    .description('Show the current reviewer')
    .action(async () => {
      await runSessionWhoami(getRuntimeOptions(program, runtime))
    })

  const workspace = program.command('workspace').description('Workspace operations')
  workspace
    .command('detect [path]')
    .description('Detect the nearest workspace')
    .action(async (path?: string) => {
      await runWorkspaceDetect(getRuntimeOptions(program, runtime), path)
    })
  workspace
    .command('bootstrap [path]')
    .description('Bootstrap a workspace through the backend')
    .option('--workspace-name <name>')
    .action(async function (this: Command, path?: string) {
      const commandOptions = this.opts<{ workspaceName?: string }>()
      await runWorkspaceBootstrap(
        getRuntimeOptions(program, runtime),
        path,
        commandOptions.workspaceName,
      )
    })

  const workflow = program.command('workflow').description('Workflow operations')
  workflow
    .command('list')
    .description('List workflows')
    .action(async () => {
      await runWorkflowList(getRuntimeOptions(program, runtime))
    })
  workflow
    .command('run <selector>')
    .description('Execute a workflow by slug, id, or file selector')
    .action(async (selector: string) => {
      await runWorkflowRun(getRuntimeOptions(program, runtime), selector)
    })
  workflow
    .command('templates')
    .description('Show built-in workflow templates')
    .action(async () => {
      await runWorkflowTemplates(getRuntimeOptions(program, runtime))
    })

  const artifact = program.command('artifact').description('Artifact operations')
  artifact
    .command('read <kind> <selector>')
    .description('Read a canonical artifact')
    .option('--raw', 'emit raw file content')
    .action(async function (this: Command, kind: string, selector: string) {
      const commandOptions = this.opts<{ raw?: boolean }>()
      await runArtifactRead(
        getRuntimeOptions(program, runtime),
        kind,
        selector,
        commandOptions.raw ?? false,
      )
    })
  artifact
    .command('diff <kind> <selector>')
    .description('Compare a canonical artifact to a candidate')
    .option('--candidate-file <path>')
    .option('--candidate-text <text>')
    .action(async function (this: Command, kind: string, selector: string) {
      const commandOptions = this.opts<{
        candidateFile?: string
        candidateText?: string
      }>()
      await runArtifactDiff(
        getRuntimeOptions(program, runtime),
        kind,
        selector,
        commandOptions.candidateFile,
        commandOptions.candidateText,
      )
    })
  artifact
    .command('write <kind> <selector>')
    .description('Write a canonical artifact safely')
    .option('--content-file <path>')
    .option('--content-text <text>')
    .option('--expected-hash <hash>')
    .action(async function (this: Command, kind: string, selector: string) {
      const commandOptions = this.opts<{
        contentFile?: string
        contentText?: string
        expectedHash?: string
      }>()
      await runArtifactWrite(
        getRuntimeOptions(program, runtime),
        kind,
        selector,
        commandOptions.contentFile,
        commandOptions.contentText,
        commandOptions.expectedHash,
      )
    })

  const skill = program.command('skill').description('Skill operations')
  skill
    .command('install')
    .description('Install the bundled skill package')
    .option('--target <path>')
    .option('--flavor <name>', 'codex or claude-code', 'codex')
    .action(async function (this: Command) {
      const commandOptions = this.opts<{ target?: string; flavor?: string }>()
      await runSkillInstall(
        getRuntimeOptions(program, runtime),
        commandOptions.target,
        commandOptions.flavor ?? 'codex',
      )
    })

  program.hook('preAction', async () => {
    await Promise.resolve()
  })

  return program
}

export async function runCli(argv = process.argv, runtime: CliRuntimeOptions = {}): Promise<ProgramRunResult> {
  const program = createProgram(runtime)
  try {
    await program.parseAsync(argv)
    return { exitCode: 0 }
  } catch (error) {
    if (error instanceof ApiError) {
      await emit(
        {
          error: {
            code: `HTTP_${String(error.status)}`,
            message: error.message,
            details: error.bodyText,
          },
        },
        'json',
      )
      return { exitCode: 1 }
    }

    await emit(
      {
        error: {
          code: 'CLI_ERROR',
          message: error instanceof Error ? error.message : String(error),
        },
      },
      'json',
    )
    return { exitCode: 1 }
  }
}

function getRuntimeOptions(program: Command, runtime: CliRuntimeOptions): CliRuntimeOptions {
  const root = program.opts<{
    baseUrl?: string
    workspace?: string
    config?: string
    session?: string
    json?: boolean
    raw?: boolean
  }>()

  const result: CliRuntimeOptions = {}
  const baseUrl = runtime.baseUrl ?? root.baseUrl
  if (baseUrl) {
    result.baseUrl = baseUrl
  }
  const configPath = runtime.configPath ?? root.config
  if (configPath) {
    result.configPath = configPath
  }
  if (runtime.json ?? root.json) {
    result.json = true
  }
  if (runtime.raw ?? root.raw) {
    result.raw = true
  }
  const sessionToken = runtime.sessionToken ?? root.session
  if (sessionToken) {
    result.sessionToken = sessionToken
  }
  const workspaceRoot = runtime.workspaceRoot ?? root.workspace
  if (workspaceRoot) {
    result.workspaceRoot = workspaceRoot
  }
  return result
}

async function loadRuntimeConfig(options: CliRuntimeOptions): Promise<CliConfig> {
  const configPath = options.configPath ?? getDefaultConfigPath()
  const fileConfig = await loadConfig(configPath)
  return resolveConfig(fileConfig, {
    ...(options.baseUrl ? { baseUrl: options.baseUrl } : {}),
    ...(options.sessionToken ? { sessionToken: options.sessionToken } : {}),
    ...(options.workspaceRoot ? { workspaceRoot: options.workspaceRoot } : {}),
  })
}

function outputMode(options: CliRuntimeOptions): OutputMode {
  if (options.raw) {
    return 'raw'
  }
  return options.json === false ? 'text' : 'json'
}

async function buildClient(options: CliRuntimeOptions): Promise<ApiClient | null> {
  const config = await loadRuntimeConfig(options)
  if (!config.baseUrl) {
    return null
  }
  return new ApiClient(
    config.sessionToken
      ? { baseUrl: config.baseUrl, sessionToken: config.sessionToken }
      : { baseUrl: config.baseUrl },
  )
}

async function runDoctor(options: CliRuntimeOptions): Promise<void> {
  const workspace = await detectWorkspace(options.workspaceRoot)
  const client = await buildClient(options)
  const health = client ? await safeGetJson<Record<string, unknown>>(client, '/health') : null
  const whoami = client ? await safeGetJson<Record<string, unknown>>(client, '/api/v1/me') : null

  await emit(
    {
      workspace,
      backend: {
        configured: Boolean(client),
        healthy: health?.status ?? null,
      },
      session: whoami,
    },
    outputMode(options),
  )
}

async function runStatus(options: CliRuntimeOptions): Promise<void> {
  const workspace = await detectWorkspace(options.workspaceRoot)
  const client = await buildClient(options)
  const health = client
    ? await safeGetJson<Record<string, unknown>>(client, '/api/v1/cli/status')
    : null

  await emit(
    {
      workspace,
      backend: health,
    },
    outputMode(options),
  )
}

async function runSessionWhoami(options: CliRuntimeOptions): Promise<void> {
  const client = await buildClient(options)
  if (!client) {
    await emit(
      { error: { code: 'NO_BACKEND', message: 'No backend base URL configured' } },
      'json',
    )
    return
  }

  const me = await client.getJson('/api/v1/me')
  await emit(me, outputMode(options))
}

async function runWorkspaceDetect(
  options: CliRuntimeOptions,
  path?: string,
): Promise<void> {
  const detection = await detectWorkspace(path ?? options.workspaceRoot)
  await emit(detection, outputMode(options))
}

async function runWorkspaceBootstrap(
  options: CliRuntimeOptions,
  path?: string,
  workspaceName?: string,
): Promise<void> {
  const basePath = resolve(path ?? options.workspaceRoot ?? process.cwd())
  const runtimeConfig = await loadRuntimeConfig(options)
  if (!runtimeConfig.baseUrl) {
    throw new Error('workspace bootstrap requires --base-url or MOLABEL_BASE_URL')
  }
  const client = new ApiClient(
    runtimeConfig.sessionToken
      ? { baseUrl: runtimeConfig.baseUrl, sessionToken: runtimeConfig.sessionToken }
      : { baseUrl: runtimeConfig.baseUrl },
  )

  const response = await client.request('/api/v1/cli/workspaces/bootstrap', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      path: basePath,
      workspace_name: workspaceName,
    }),
  })

  const body = (await response.json()) as Record<string, unknown>
  const setCookie = readSetCookieHeaders(response.headers)
  const sessionToken = extractSessionTokenFromSetCookie(setCookie)
  if (sessionToken) {
    const configPath = options.configPath ?? getDefaultConfigPath()
    const current = await loadConfig(configPath)
    await saveConfig(
      {
        ...current,
        ...(runtimeConfig.baseUrl ? { baseUrl: runtimeConfig.baseUrl } : {}),
        ...(sessionToken ? { sessionToken } : {}),
        workspaceRoot: basePath,
      },
      configPath,
    )
  }

  await emit(
    {
      workspace: body,
      sessionToken: sessionToken ?? null,
    },
    outputMode(options),
  )
}

async function runWorkflowList(options: CliRuntimeOptions): Promise<void> {
  const client = await buildClient(options)
  if (client) {
    const response = await client.getJson<{ items?: unknown[] }>('/api/v1/workflows')
    await emit(response, outputMode(options))
    return
  }

  const workspace = await detectWorkspace(options.workspaceRoot)
  if (!workspace.rootDir) {
    await emit({ items: [] }, outputMode(options))
    return
  }

  const workflows = await listLocalVersionedArtifacts(workspace.rootDir, 'workbench/workflows')
  await emit({ items: workflows }, outputMode(options))
}

async function runWorkflowRun(
  options: CliRuntimeOptions,
  selector: string,
): Promise<void> {
  const client = await buildClient(options)
  if (!client) {
    throw new Error('workflow run requires --base-url or MOLABEL_BASE_URL')
  }

  const workflow = await resolveWorkflowRemote(client, selector)
  const execution = await client.postJson<Record<string, unknown>>(
    `/api/v1/workflows/${workflow.workflow_id}/execute`,
    {},
  )
  await emit(execution, outputMode(options))
}

async function runWorkflowTemplates(options: CliRuntimeOptions): Promise<void> {
  const client = await buildClient(options)
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

  await emit(WORKFLOW_TEMPLATES.templates, outputMode(options))
}

async function runArtifactRead(
  options: CliRuntimeOptions,
  kind: string,
  selector: string,
  raw = false,
): Promise<void> {
  const workspace = await detectWorkspace(options.workspaceRoot)
  if (!workspace.rootDir) {
    throw new Error('No MoLabel workspace detected')
  }

  const client = await buildClient(options)
  if (client) {
    const response = await safePostJson<Record<string, unknown>>(
      client,
      '/api/v1/cli/artifacts/read',
      {
        kind: normalizeArtifactKindForApi(kind),
        selector: normalizeArtifactSelector(selector),
        workspace_root: workspace.rootDir,
      },
    )
    if (response) {
      if (raw && typeof response.content === 'string') {
        await emit(response.content, 'raw')
        return
      }
      await emit(response, outputMode(options))
      return
    }
  }

  const resolved = await resolveArtifact(
    workspace.rootDir,
    kind,
    normalizeArtifactSelector(selector),
  )
  const content = await readTextFile(resolved.path)
  if (raw) {
    await emit(content, 'raw')
    return
  }

  await emit(
    {
      ...resolved,
      content,
      hash: sha256(content),
    },
    outputMode(options),
  )
}

async function runArtifactDiff(
  options: CliRuntimeOptions,
  kind: string,
  selector: string,
  candidateFile?: string,
  candidateText?: string,
): Promise<void> {
  const workspace = await detectWorkspace(options.workspaceRoot)
  if (!workspace.rootDir) {
    throw new Error('No MoLabel workspace detected')
  }

  const resolved = await resolveArtifact(
    workspace.rootDir,
    kind,
    normalizeArtifactSelector(selector),
  )
  const current = await readTextFile(resolved.path)
  const candidate = await readInputText({
    file: candidateFile ? resolve(candidateFile) : undefined,
    text: candidateText,
    allowStdin: true,
    errorMessage: 'artifact diff requires --candidate-file, --candidate-text, or piped stdin',
  })

  const client = await buildClient(options)
  if (client) {
    const response = await safePostJson<Record<string, unknown>>(
      client,
      '/api/v1/cli/artifacts/diff',
      {
        kind: normalizeArtifactKindForApi(kind),
        selector: normalizeArtifactSelector(selector),
        content: candidate,
        workspace_root: workspace.rootDir,
      },
    )
    if (response) {
      await emit(response, outputMode(options))
      return
    }
  }
  const result = diffText(current, candidate, resolved.path)
  await emit({ ...result, selector, kind }, outputMode(options))
}

async function runArtifactWrite(
  options: CliRuntimeOptions,
  kind: string,
  selector: string,
  contentFile?: string,
  contentText?: string,
  expectedHash?: string,
): Promise<void> {
  const workspace = await detectWorkspace(options.workspaceRoot)
  if (!workspace.rootDir) {
    throw new Error('No MoLabel workspace detected')
  }

  const resolved = await resolveArtifact(
    workspace.rootDir,
    kind,
    normalizeArtifactSelector(selector),
  )
  const content = await readInputText({
    file: contentFile ? resolve(contentFile) : undefined,
    text: contentText,
    allowStdin: true,
    errorMessage: 'artifact write requires --content-file, --content-text, or piped stdin',
  })

  const client = await buildClient(options)
  if (client) {
    const response = await safePostJson<Record<string, unknown>>(
      client,
      '/api/v1/cli/artifacts/write',
      {
        kind: normalizeArtifactKindForApi(kind),
        selector: normalizeArtifactSelector(selector),
        content,
        expected_hash: expectedHash,
        workspace_root: workspace.rootDir,
      },
    )
    if (response) {
      await emit(response, outputMode(options))
      return
    }
  }

  const current = await safeReadText(resolved.path)
  const currentHash = current ? sha256(current) : null
  if (expectedHash && currentHash && expectedHash !== currentHash) {
    throw new Error(`expected hash mismatch for ${resolved.path}`)
  }

  await atomicWriteTextFile(resolved.path, content)
  await emit(
    {
      path: resolved.path,
      hash: sha256(content),
      selector,
      kind,
      expectedHash: expectedHash ?? null,
    },
    outputMode(options),
  )
}

async function runSkillInstall(
  options: CliRuntimeOptions,
  target?: string,
  flavor: string = 'codex',
): Promise<void> {
  if (flavor !== 'codex' && flavor !== 'claude-code') {
    throw new Error('skill flavor must be codex or claude-code')
  }

  const packageRoot = dirname(fileURLToPath(import.meta.url))
  const root = resolve(packageRoot, '..', '..')
  const targetRoot = resolve(target ?? getDefaultSkillTarget())
  const result = await installSkillBundle(root, targetRoot, flavor)
  await emit(result, outputMode(options))
}

async function safeGetJson<T>(client: ApiClient, path: string): Promise<T | null> {
  try {
    return await client.getJson<T>(path)
  } catch {
    return null
  }
}

async function safePostJson<T>(
  client: ApiClient,
  path: string,
  body: unknown,
): Promise<T | null> {
  try {
    return await client.postJson<T>(path, body)
  } catch {
    return null
  }
}

async function safeReadText(path: string): Promise<string | null> {
  try {
    return await readTextFile(path)
  } catch {
    return null
  }
}

async function listLocalVersionedArtifacts(
  rootDir: string,
  directory: string,
): Promise<Array<Record<string, string>>> {
  const fullDirectory = join(rootDir, directory)
  const entries = await readdir(fullDirectory, { withFileTypes: true }).catch(() => [])
  return entries
    .filter((entry) => entry.isFile() && entry.name.endsWith('.yaml'))
    .map((entry) => ({
      file_path: join(fullDirectory, entry.name),
      name: entry.name,
    }))
}

async function resolveWorkflowRemote(
  client: ApiClient,
  selector: string,
): Promise<{ workflow_id: string; workflow_slug?: string }> {
  const workflows = await client.getJson<{ items?: Array<Record<string, unknown>> }>('/api/v1/workflows')
  const items = workflows.items ?? []
  const normalized = selector.trim()
  const found = items.find((item) => {
    const workflowId = readStringField(item.workflow_id) ?? readStringField(item.id)
    const workflowSlug = readStringField(item.workflow_slug)
    return workflowId === normalized || workflowSlug === normalized
  })

  if (!found) {
    throw new Error(`Workflow not found: ${selector}`)
  }

  const resolved: { workflow_id: string; workflow_slug?: string } = {
    workflow_id:
      readStringField(found.workflow_id) ?? readStringField(found.id) ?? '',
  }
  if (typeof found.workflow_slug === 'string') {
    resolved.workflow_slug = found.workflow_slug
  }
  return resolved
}

function getDefaultSkillTarget(): string {
  const codexHome = process.env.CODEX_HOME
  if (codexHome && codexHome.trim()) {
    return join(codexHome, 'skills')
  }

  return join(homedir(), '.codex', 'skills')
}

function readStringField(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined
}

function normalizeArtifactKindForApi(kind: string): string {
  if (kind === 'workspace') {
    return 'workspace_manifest'
  }
  if (kind === 'task-schema') {
    return 'task_schema'
  }
  return kind
}
