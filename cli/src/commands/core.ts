import type { Command } from 'commander'

import { COMMAND_MANIFEST } from '../manifest/commands.js'
import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import {
  buildClient,
  detectWorkspaceRoot,
  getRuntimeOptions,
  outputMode,
  safeGetJson,
} from './context.js'

export function registerCoreCommands(program: Command, runtime: CliRuntimeOptions): void {
  program.command('doctor').description('Check environment health').action(async () => {
    await runDoctor(getRuntimeOptions(program, runtime))
  })

  program.command('status').description('Show workspace and backend status').action(async () => {
    await runStatus(getRuntimeOptions(program, runtime))
  })

  program.command('manifest').description('Print the CLI manifest').option('--json').action(async () => {
    await emit(COMMAND_MANIFEST, 'json')
  })
}

async function runDoctor(options: CliRuntimeOptions): Promise<void> {
  const workspace = await detectWorkspaceRoot(options.workspaceRoot)
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
  const workspace = await detectWorkspaceRoot(options.workspaceRoot)
  const client = await buildClient(options)
  const health = client ? await safeGetJson<Record<string, unknown>>(client, '/api/v1/cli/status') : null

  await emit(
    {
      workspace,
      backend: health,
    },
    outputMode(options),
  )
}
