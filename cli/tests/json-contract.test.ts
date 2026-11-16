import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import type { Command } from 'commander'
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import { createProgram } from '../src/cli.js'
import {
  parseStdoutJson,
  readErrorCode,
  runCliCapture,
  startMockApi,
  type CliResult,
} from './support/cli-harness.js'

interface LeafCommand {
  name: string
  command: Command
  argv: string[]
}

function leafCommands(command: Command, path: string[] = []): LeafCommand[] {
  if (command.commands.length === 0) {
    const operands = command.registeredArguments
      .filter((argument) => argument.required)
      .map(() => 'placeholder')
    const requiredOptions = command.options
      .filter((option) => option.mandatory)
      .flatMap((option) => [option.long ?? option.flags, 'placeholder'])
    return [
      {
        name: path.join(' '),
        command,
        argv: [...path, ...operands, ...requiredOptions],
      },
    ]
  }
  return command.commands.flatMap((sub) =>
    leafCommands(sub, [...path, sub.name()]),
  )
}

interface EnvelopeError {
  code: string
  message: unknown
}

function readEnvelopeError(value: unknown): EnvelopeError | undefined {
  const { error } = (value ?? {}) as {
    error?: { code?: unknown; message?: unknown }
  }
  return typeof error?.code === 'string'
    ? { code: error.code, message: error.message }
    : undefined
}

function expectContract(result: CliResult): EnvelopeError | undefined {
  let value: unknown
  expect(
    () => {
      value = JSON.parse(result.stdout)
    },
    `stdout is one JSON document: ${result.stdout.slice(0, 200)}`,
  ).not.toThrow()
  const error = readEnvelopeError(value)
  if (result.exitCode === 0) {
    expect(error, 'exit 0 prints a result, not an error').toBeUndefined()
    return undefined
  }
  expect(result.exitCode).toBe(1)
  expect(error).toMatchObject({
    code: expect.stringMatching(/^[A-Z][A-Z0-9_]*$/) as unknown,
    message: expect.any(String) as unknown,
  })
  return error
}

const PROGRAM = createProgram()
const LEAVES = leafCommands(PROGRAM)

describe('JSON contract', () => {
  it.each([
    ['session', 'whoami'],
    ['queue', 'list'],
    ['workflow', 'run', 'wf'],
  ])(
    '%s %s fails with NO_BACKEND when no backend is configured',
    async (...command: string[]) => {
      const result = await runCliCapture(command)

      expect(result.exitCode).toBe(1)
      expect(readErrorCode(result)).toBe('NO_BACKEND')
      expect(parseStdoutJson(result)).toMatchObject({
        error: { message: expect.stringContaining('--base-url') as unknown },
      })
    },
  )

  it('carries the backend error message and body in an HTTP error', async () => {
    const backendError = {
      error: { code: 'BAD_REQUEST', message: 'The workspace has 2 datasets' },
    }
    const api = await startMockApi({
      'GET /api/v1/queues': () => ({ status: 400, body: backendError }),
    })
    try {
      const result = await runCliCapture([
        '--base-url',
        api.url,
        'queue',
        'list',
      ])

      expect(result.exitCode).toBe(1)
      expect(parseStdoutJson(result)).toEqual({
        error: {
          code: 'HTTP_400',
          message: 'The workspace has 2 datasets',
          details: backendError,
        },
      })
    } finally {
      await api.close()
    }
  })

  it('reports an unreachable backend as BACKEND_UNREACHABLE', async () => {
    const api = await startMockApi({})
    await api.close()

    const result = await runCliCapture(['--base-url', api.url, 'queue', 'list'])

    expect(result.exitCode).toBe(1)
    expect(readErrorCode(result)).toBe('BACKEND_UNREACHABLE')
    expect(parseStdoutJson(result)).toMatchObject({
      error: { message: expect.stringContaining(api.url) as unknown },
    })
  })

  it('gives no command an option that a global option would swallow', () => {
    const globalFlags = new Set(PROGRAM.options.map((option) => option.long))
    const shadowed = LEAVES.flatMap(({ name, command }) =>
      command.options
        .filter((option) => globalFlags.has(option.long))
        .map((option) => `${name} ${String(option.long)}`),
    )

    expect(shadowed).toEqual([])
  })

  it('release certify sends --release-version as the release version', async () => {
    const api = await startMockApi({
      'POST /api/v1/releases': () => ({
        status: 201,
        body: { release_id: 'rel-1' },
      }),
    })
    try {
      const result = await runCliCapture([
        '--base-url',
        api.url,
        'release',
        'certify',
        '--release-version',
        '1.2.0',
        '--workspace-id',
        'ws-1',
      ])

      expect(result.exitCode).toBe(0)
      expect(parseStdoutJson(result)).toEqual({ release_id: 'rel-1' })
      expect(api.requests[0]?.body).toMatchObject({ version: '1.2.0' })
    } finally {
      await api.close()
    }
  })

  it('artifact read --raw prints only the artifact content', async () => {
    const workspace = await mkdtemp(join(tmpdir(), 'molabel-raw-'))
    try {
      await writeFile(
        join(workspace, 'workbench.project.yaml'),
        'name: raw-test\n',
      )

      const result = await runCliCapture([
        '--workspace',
        workspace,
        'artifact',
        'read',
        'workspace',
        'workspace',
        '--raw',
      ])

      expect(result.exitCode).toBe(0)
      expect(result.stdout).toBe('name: raw-test\n')
    } finally {
      await rm(workspace, { recursive: true, force: true })
    }
  })
})

interface BackendState {
  name: string
  start: () => Promise<{ baseUrl: string | null; close: () => Promise<void> }>
  check: (error: EnvelopeError) => void
}

const BACKEND_STATES: BackendState[] = [
  {
    name: 'no backend configured',
    start: () =>
      Promise.resolve({ baseUrl: null, close: () => Promise.resolve() }),
    check: (error) => {
      if (String(error.message).includes('--base-url')) {
        expect(error.code).toBe('NO_BACKEND')
      }
    },
  },
  {
    name: 'a backend answering {} to everything',
    start: async () => {
      const api = await startMockApi({}, () => ({ body: {} }))
      return { baseUrl: api.url, close: api.close }
    },
    check: () => undefined,
  },
  {
    name: 'a backend failing with 500',
    start: async () => {
      const api = await startMockApi({}, () => ({
        status: 500,
        body: {
          error: { code: 'INTERNAL_ERROR', message: 'backend exploded' },
        },
      }))
      return { baseUrl: api.url, close: api.close }
    },
    check: (error) => {
      if (error.code === 'HTTP_500') {
        expect(error.message).toBe('backend exploded')
      }
    },
  },
  {
    name: 'an unreachable backend',
    start: async () => {
      const api = await startMockApi({})
      await api.close()
      return { baseUrl: api.url, close: () => Promise.resolve() }
    },
    check: (error) => {
      expect(error.message).not.toBe('fetch failed')
    },
  },
]

describe.each(BACKEND_STATES)('every command with $name', (state) => {
  const previousCwd = process.cwd()
  const previousCodexHome = process.env.CODEX_HOME
  const stdinTty = Object.getOwnPropertyDescriptor(process.stdin, 'isTTY')
  let sandbox = ''
  let baseUrl: string | null = null
  let close = () => Promise.resolve()

  beforeAll(async () => {
    sandbox = await mkdtemp(join(tmpdir(), 'molabel-contract-'))
    process.chdir(sandbox)
    process.env.CODEX_HOME = join(sandbox, 'codex')
    // The runner's stdin is a pipe that never closes; commands that fall back
    // to reading stdin would wait on it forever.
    Object.defineProperty(process.stdin, 'isTTY', {
      value: true,
      configurable: true,
    })
    ;({ baseUrl, close } = await state.start())
  })

  afterAll(async () => {
    await close()
    if (stdinTty) {
      Object.defineProperty(process.stdin, 'isTTY', stdinTty)
    } else {
      Reflect.deleteProperty(process.stdin, 'isTTY')
    }
    if (previousCodexHome === undefined) {
      Reflect.deleteProperty(process.env, 'CODEX_HOME')
    } else {
      process.env.CODEX_HOME = previousCodexHome
    }
    process.chdir(previousCwd)
    await rm(sandbox, { recursive: true, force: true })
  })

  it.each(LEAVES)('$name', async ({ argv }) => {
    const backend = baseUrl ? ['--base-url', baseUrl] : []

    const result = await runCliCapture([
      ...backend,
      '--workspace',
      sandbox,
      ...argv,
    ])

    const error = expectContract(result)
    if (error) {
      state.check(error)
    }
  })
})
