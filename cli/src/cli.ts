import { Command, CommanderError } from 'commander'

import { ApiError } from './client/http.js'
import { registerCommands } from './commands/index.js'
import { CliFailure } from './errors.js'
import type { CliRuntimeOptions } from './types.js'

const VERSION = '0.1.0'

export interface ProgramRunResult {
  exitCode: number
}

export function createProgram(runtime: CliRuntimeOptions = {}): Command {
  const program = new Command()
  program.name('molabel')
  program.description('MoLabel agent CLI')
  program.exitOverride()

  program
    .option('--base-url <url>', 'backend base URL')
    .option('--workspace <path>', 'workspace root override')
    .option('--config <path>', 'CLI config path')
    .option('--session <token>', 'session token override')
    .option('--json', 'force JSON output')
    .option('--raw', 'emit raw output where supported')
    .option('-V, --version', 'output the version number')

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
    if (requestsVersion(program, argv.slice(2))) {
      process.stdout.write(`${VERSION}
`)
      return { exitCode: 0 }
    }
    await program.parseAsync(argv)
    const exitCode = typeof process.exitCode === 'number' ? process.exitCode : 0
    return { exitCode }
  } catch (error) {
    if (error instanceof CommanderError && error.exitCode === 0) {
      return { exitCode: 0 }
    }
    const { emit } = await import('./output.js')
    await emit({ error: toErrorBody(error) }, 'json')
    return { exitCode: error instanceof CommanderError ? error.exitCode : 1 }
  } finally {
    process.exitCode = previousExitCode
  }
}

// Commander recognises root options after subcommands too, so its built-in
// version option would print the version for `release certify --version 1.0`.
function requestsVersion(program: Command, args: string[]): boolean {
  const { operands, unknown } = program.parseOptions(args)
  if (program.opts<{ version?: boolean }>().version !== true) {
    return false
  }
  if (operands.length === 0 && unknown.length === 0) {
    return true
  }
  throw new CommanderError(
    1,
    'molabel.version',
    "--version is only accepted on its own, as 'molabel --version'",
  )
}

interface ErrorBody {
  code: string
  message: string
  details?: unknown
}

function toErrorBody(error: unknown): ErrorBody {
  if (error instanceof CommanderError) {
    return {
      code: 'USAGE_ERROR',
      message:
        error.code === 'commander.help'
          ? 'A subcommand is required. Run with --help to list them.'
          : error.message,
    }
  }
  if (error instanceof ApiError) {
    const body = parseJsonOrNull(error.bodyText)
    return {
      code: `HTTP_${String(error.status)}`,
      message: readBackendMessage(body) ?? error.message,
      details: body ?? error.bodyText,
    }
  }
  if (error instanceof CliFailure) {
    return error.details === undefined
      ? { code: error.code, message: error.message }
      : { code: error.code, message: error.message, details: error.details }
  }
  return {
    code: 'CLI_ERROR',
    message: error instanceof Error ? error.message : String(error),
  }
}

function parseJsonOrNull(text: string): unknown {
  try {
    return JSON.parse(text) as unknown
  } catch {
    return null
  }
}

function readBackendMessage(body: unknown): string | undefined {
  if (!body || typeof body !== 'object') {
    return undefined
  }
  const { error, detail } = body as { error?: unknown; detail?: unknown }
  if (error && typeof error === 'object') {
    const { message } = error as { message?: unknown }
    if (typeof message === 'string') {
      return message
    }
  }
  return typeof detail === 'string' ? detail : undefined
}
