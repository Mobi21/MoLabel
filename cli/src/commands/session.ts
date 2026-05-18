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
  getRuntimeOptions,
  loadRuntimeConfig,
  outputMode,
  resolveWorkspaceId,
} from './context.js'

export function registerSessionCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const session = program.command('session').description('Session operations')
  session
    .command('whoami')
    .description('Show the current reviewer')
    .action(async () => {
      await runSessionWhoami(getRuntimeOptions(program, runtime))
    })

  session
    .command('list-reviewers')
    .description('List reviewer profiles')
    .option('--workspace-id <id>', 'Workspace ID filter')
    .option('--all', 'Include inactive profiles')
    .action(async function (this: Command) {
      await runSessionListReviewers(
        getRuntimeOptions(program, runtime),
        this.opts<{ workspaceId?: string; all?: boolean }>(),
      )
    })

  session
    .command('select <reviewerId>')
    .description('Create a session for a reviewer profile')
    .action(async (reviewerId: string) => {
      await runSessionSelect(getRuntimeOptions(program, runtime), reviewerId)
    })

  session
    .command('switch <reviewerId>')
    .description('Switch to a different reviewer profile')
    .action(async (reviewerId: string) => {
      await runSessionSwitch(getRuntimeOptions(program, runtime), reviewerId)
    })
}

async function runSessionWhoami(options: CliRuntimeOptions): Promise<void> {
  const client = await buildClient(options)
  if (!client) {
    await emit(
      {
        error: {
          code: 'NO_BACKEND',
          message: 'No backend base URL configured',
        },
      },
      'json',
    )
    return
  }

  const me = await client.getJson('/api/v1/me')
  await emit(me, outputMode(options))
}

async function runSessionListReviewers(
  options: CliRuntimeOptions,
  commandOptions: { workspaceId?: string; all?: boolean },
): Promise<void> {
  const client = await requireBackendClient(options, 'session list-reviewers')
  const workspaceId = await resolveWorkspaceId(
    options,
    commandOptions.workspaceId,
  )
  const response = await client.getJson(
    `/api/v1/reviewer-profiles${buildQuery({
      workspace_id: workspaceId,
      active_only: commandOptions.all ? 'false' : 'true',
    })}`,
  )
  await emit({ items: response }, outputMode(options))
}

async function runSessionSelect(
  options: CliRuntimeOptions,
  reviewerId: string,
): Promise<void> {
  await runSessionMutation(
    options,
    '/api/v1/sessions',
    reviewerId,
    'session_created',
  )
}

async function runSessionSwitch(
  options: CliRuntimeOptions,
  reviewerId: string,
): Promise<void> {
  await runSessionMutation(
    options,
    '/api/v1/sessions/switch',
    reviewerId,
    'session_switched',
  )
}

async function runSessionMutation(
  options: CliRuntimeOptions,
  path: string,
  reviewerId: string,
  message: string,
): Promise<void> {
  const client = await requireBackendClient(options, message)
  const response = await client.request(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ reviewer_id: reviewerId }),
  })

  const body = (await response.json()) as Record<string, unknown>
  const setCookie = readSetCookieHeaders(response.headers)
  const sessionToken = extractSessionTokenFromSetCookie(setCookie)
  if (sessionToken) {
    const runtimeConfig = await loadRuntimeConfig(options)
    const configPath = options.configPath ?? getDefaultConfigPath()
    const current = await loadConfig(configPath)
    await saveConfig(
      {
        ...current,
        ...(runtimeConfig.baseUrl ? { baseUrl: runtimeConfig.baseUrl } : {}),
        sessionToken,
        ...(runtimeConfig.workspaceRoot
          ? { workspaceRoot: runtimeConfig.workspaceRoot }
          : {}),
      },
      configPath,
    )
  }

  await emit(
    {
      reviewer: body,
      sessionToken: sessionToken ?? null,
    },
    outputMode(options),
  )
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
