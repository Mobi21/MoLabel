import { resolve } from 'node:path'

import type { Command } from 'commander'

import { extractSessionTokenFromSetCookie, readSetCookieHeaders } from '../client/session.js'
import { getDefaultConfigPath, loadConfig, saveConfig } from '../config.js'
import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import {
  buildClient,
  detectWorkspaceRoot,
  getRuntimeOptions,
  loadRuntimeConfig,
  outputMode,
} from './context.js'

export function registerWorkspaceCommands(program: Command, runtime: CliRuntimeOptions): void {
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
}

async function runWorkspaceDetect(options: CliRuntimeOptions, path?: string): Promise<void> {
  const detection = await detectWorkspaceRoot(path ?? options.workspaceRoot)
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
  const client = await buildClient(options)
  if (!client) {
    throw new Error('workspace bootstrap requires --base-url or MOLABEL_BASE_URL')
  }

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
        sessionToken,
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
