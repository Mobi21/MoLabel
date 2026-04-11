import { Command } from 'commander'

import { ApiError } from './client/http.js'
import { registerCommands } from './commands/index.js'
import type { CliRuntimeOptions } from './types.js'

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

  registerCommands(program, runtime)

  program.hook('preAction', async () => {
    await Promise.resolve()
  })

  return program
}

export async function runCli(
  argv = process.argv,
  runtime: CliRuntimeOptions = {},
): Promise<ProgramRunResult> {
  const program = createProgram(runtime)
  const previousExitCode = process.exitCode
  try {
    await program.parseAsync(argv)
    const exitCode = typeof process.exitCode === 'number' ? process.exitCode : 0
    return { exitCode }
  } catch (error) {
    const { emit } = await import('./output.js')
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
  } finally {
    process.exitCode = previousExitCode
  }
}
