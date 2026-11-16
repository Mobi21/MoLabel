import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import type { Command } from 'commander'
import { describe, expect, it } from 'vitest'

import { createProgram } from '../src/cli.js'
import {
  parseStdoutJson,
  readErrorCode,
  runCliCapture,
  startMockApi,
} from './support/cli-harness.js'

interface LeafCommand {
  name: string
  command: Command
}

function leafCommands(command: Command, path: string[] = []): LeafCommand[] {
  if (command.commands.length === 0) {
    return [{ name: path.join(' '), command }]
  }
  return command.commands.flatMap((sub) =>
    leafCommands(sub, [...path, sub.name()]),
  )
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
