import { readdir, readFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { homedir } from 'node:os'
import { fileURLToPath } from 'node:url'

import { parse as parseYaml } from 'yaml'

import { ApiClient } from '../client/http.js'
import { detectWorkspace, normalizeArtifactSelector, resolveArtifact } from '../workspace-context.js'
import { getDefaultConfigPath, loadConfig, resolveConfig, saveConfig } from '../config.js'
import type { CliConfig, CliRuntimeOptions, OutputMode, WorkspaceDetection } from '../types.js'

export async function loadRuntimeConfig(options: CliRuntimeOptions): Promise<CliConfig> {
  const configPath = options.configPath ?? getDefaultConfigPath()
  const fileConfig = await loadConfig(configPath)
  return resolveConfig(fileConfig, {
    ...(options.baseUrl ? { baseUrl: options.baseUrl } : {}),
    ...(options.sessionToken ? { sessionToken: options.sessionToken } : {}),
    ...(options.workspaceRoot ? { workspaceRoot: options.workspaceRoot } : {}),
  })
}

export function outputMode(options: CliRuntimeOptions): OutputMode {
  if (options.raw) {
    return 'raw'
  }
  return options.json === false ? 'text' : 'json'
}

export async function buildClient(options: CliRuntimeOptions): Promise<ApiClient | null> {
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

export async function requireClient(options: CliRuntimeOptions): Promise<ApiClient> {
  const client = await buildClient(options)
  if (!client) {
    throw new Error('This command requires --base-url or MOLABEL_BASE_URL')
  }
  return client
}

export async function safeGetJson<T>(client: ApiClient, path: string): Promise<T | null> {
  try {
    return await client.getJson<T>(path)
  } catch {
    return null
  }
}

export async function safePostJson<T>(
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

export async function safeReadText(path: string): Promise<string | null> {
  try {
    return await readFile(path, 'utf8')
  } catch {
    return null
  }
}

export async function readWorkspaceManifest(
  options: CliRuntimeOptions,
): Promise<Record<string, unknown> | null> {
  const workspace = await detectWorkspaceRoot(options.workspaceRoot)
  if (!workspace.rootDir || !workspace.manifestPath) {
    return null
  }
  const raw = await safeReadText(workspace.manifestPath)
  if (!raw) {
    return null
  }
  const parsed = parseYaml(raw)
  return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null
}

export async function resolveWorkspaceId(
  options: CliRuntimeOptions,
  explicitWorkspaceId?: string,
): Promise<string> {
  if (explicitWorkspaceId?.trim()) {
    return explicitWorkspaceId.trim()
  }

  const manifest = await readWorkspaceManifest(options)
  const workspaceId =
    readStringField(manifest?.workspace_id) ??
    readStringField(manifest?.workspaceId) ??
    readStringField(manifest?.id)
  if (!workspaceId) {
    throw new Error('Workspace ID is required. Pass --workspace-id or run inside a workspace with workbench.project.yaml')
  }
  return workspaceId
}

export async function readJsonInput(options: {
  file?: string
  text?: string
  stdin?: string
  errorMessage: string
}): Promise<unknown> {
  const raw =
    (options.file ? await safeReadText(options.file) : null) ??
    options.text ??
    options.stdin ??
    null
  if (!raw || !raw.trim()) {
    throw new Error(options.errorMessage)
  }
  try {
    return JSON.parse(raw)
  } catch (error) {
    const reason = error instanceof Error ? error.message : 'Invalid JSON'
    throw new Error(`Failed to parse JSON input: ${reason}`)
  }
}

export async function listLocalVersionedArtifacts(
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

export async function resolveWorkflowRemote(
  client: ApiClient,
  selector: string,
): Promise<{ workflow_id: string; workflow_slug?: string }> {
  const workflows = await client.getJson<{ items?: Array<Record<string, unknown>> }>(
    '/api/v1/workflows',
  )
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
    workflow_id: readStringField(found.workflow_id) ?? readStringField(found.id) ?? '',
  }
  if (typeof found.workflow_slug === 'string') {
    resolved.workflow_slug = found.workflow_slug
  }
  return resolved
}

export function getDefaultSkillTarget(): string {
  const codexHome = process.env.CODEX_HOME
  if (codexHome && codexHome.trim()) {
    return join(codexHome, 'skills')
  }

  return join(homedir(), '.codex', 'skills')
}

export function normalizeArtifactKindForApi(kind: string): string {
  if (kind === 'workspace') {
    return 'workspace_manifest'
  }
  if (kind === 'task-schema') {
    return 'task_schema'
  }
  return kind
}

export { normalizeArtifactSelector, resolveArtifact } from '../workspace-context.js'

export function readStringField(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined
}

export function getRuntimeOptions(program: import('commander').Command, runtime: CliRuntimeOptions): CliRuntimeOptions {
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

export async function detectWorkspaceRoot(path?: string): Promise<WorkspaceDetection> {
  return detectWorkspace(path)
}

export async function writeResolvedConfig(
  config: CliConfig,
  options: CliRuntimeOptions,
): Promise<void> {
  const configPath = options.configPath ?? getDefaultConfigPath()
  await saveConfig(config, configPath)
}

export function cliPackageRoot(): string {
  const packageRoot = dirname(fileURLToPath(import.meta.url))
  return resolve(packageRoot, '..', '..')
}

export async function resolveArtifactPath(
  workspaceRoot: string,
  kind: string,
  selector: string,
): Promise<Awaited<ReturnType<typeof resolveArtifact>>> {
  return resolveArtifact(workspaceRoot, kind, normalizeArtifactSelector(selector))
}
