import { readdir, readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import type { Command } from 'commander'

import {
  extractSessionTokenFromSetCookie,
  readSetCookieHeaders,
} from '../client/session.js'
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

export function registerWorkspaceCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const workspace = program
    .command('workspace')
    .description('Workspace operations')
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
  workspace
    .command('diff')
    .description('Show semantic workspace proposals for a run')
    .requiredOption('--run <runId>', 'Run ID')
    .action(async function (this: Command) {
      await runWorkspaceDiff(
        getRuntimeOptions(program, runtime),
        this.opts<{ run: string }>().run,
      )
    })
  workspace
    .command('apply')
    .description('Accept all proposed workspace changes for a run')
    .requiredOption('--run <runId>', 'Run ID')
    .action(async function (this: Command) {
      await runWorkspaceDecision(
        getRuntimeOptions(program, runtime),
        this.opts<{ run: string }>().run,
        'accept',
      )
    })
  workspace
    .command('reject')
    .description('Reject all proposed workspace changes for a run')
    .requiredOption('--run <runId>', 'Run ID')
    .action(async function (this: Command) {
      await runWorkspaceDecision(
        getRuntimeOptions(program, runtime),
        this.opts<{ run: string }>().run,
        'reject',
      )
    })
}

async function runWorkspaceDetect(
  options: CliRuntimeOptions,
  path?: string,
): Promise<void> {
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
    throw new Error(
      'workspace bootstrap requires --base-url or MOLABEL_BASE_URL',
    )
  }
  const client = await buildClient(options)
  if (!client) {
    throw new Error(
      'workspace bootstrap requires --base-url or MOLABEL_BASE_URL',
    )
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

async function runWorkspaceDiff(
  options: CliRuntimeOptions,
  runId: string,
): Promise<void> {
  const proposals = await proposalsForRun(options, runId)
  await emit(
    {
      run_id: runId,
      proposal_count: proposals.length,
      proposals,
    },
    outputMode(options),
  )
}

async function runWorkspaceDecision(
  options: CliRuntimeOptions,
  runId: string,
  decision: 'accept' | 'reject',
): Promise<void> {
  const proposals = await proposalsForRun(options, runId)
  const client = await buildClient(options)
  if (!client) {
    throw new Error('workspace apply/reject requires --base-url or MOLABEL_BASE_URL')
  }
  const decided = []
  for (const proposal of proposals) {
    const proposalId = readString(proposal.proposal_id)
    if (!proposalId || proposal.status !== 'proposed') {
      continue
    }
    const response = await client.postJson<Record<string, unknown>>(
      `/api/v1/cli/artifacts/proposals/${proposalId}/decision`,
      {
        decision,
        workspace_root: await workspaceRoot(options),
        notes: `Workspace ${decision} for run ${runId}`,
      },
    )
    decided.push(response)
  }
  await emit(
    {
      run_id: runId,
      decision,
      decided_count: decided.length,
      proposals: decided,
    },
    outputMode(options),
  )
}

async function proposalsForRun(
  options: CliRuntimeOptions,
  runId: string,
): Promise<Array<Record<string, unknown>>> {
  const root = await workspaceRoot(options)
  const proposalDir = resolve(root, 'workbench', 'proposals', 'artifacts')
  const entries = await readdir(proposalDir).catch(() => [])
  const proposals = []
  for (const entry of entries) {
    if (!entry.endsWith('.json')) {
      continue
    }
    const raw = await readFile(resolve(proposalDir, entry), 'utf8')
    const parsed = JSON.parse(raw) as Record<string, unknown>
    if (parsed.run_id === runId) {
      proposals.push(parsed)
    }
  }
  return proposals
}

async function workspaceRoot(options: CliRuntimeOptions): Promise<string> {
  const detection = await detectWorkspaceRoot(options.workspaceRoot)
  if (!detection.rootDir) {
    throw new Error('No MoLabel workspace detected')
  }
  return detection.rootDir
}

function readString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}
