import { readFile } from 'node:fs/promises'

import { describe, expect, it } from 'vitest'

import { readErrorCode, runCliCapture } from './support/cli-harness.js'

describe('help and version', () => {
  it('prints top-level help and exits 0', async () => {
    const result = await runCliCapture(['--help'])

    expect(result.exitCode).toBe(0)
    expect(result.stdout).toContain('Usage: molabel')
    expect(result.stdout).not.toContain('"error"')
  })

  it('prints subcommand help and exits 0', async () => {
    const result = await runCliCapture(['workflow', 'run', '--help'])

    expect(result.exitCode).toBe(0)
    expect(result.stdout).toContain('Usage: molabel workflow run')
    expect(result.stdout).not.toContain('"error"')
  })

  it('prints the package version and exits 0', async () => {
    const packageJson = JSON.parse(
      await readFile(new URL('../package.json', import.meta.url), 'utf8'),
    ) as { version: string }

    const result = await runCliCapture(['--version'])

    expect(result.exitCode).toBe(0)
    expect(result.stdout.trim()).toBe(packageJson.version)
  })

  it('lists --version in top-level help', async () => {
    const result = await runCliCapture(['--help'])

    expect(result.stdout).toContain('-V, --version')
  })

  it.each([
    [['release', 'certify', '--version', '1.0.0']],
    [['release', 'list', '--version']],
    [['workflow', 'run', 'demo', '-V']],
  ])('rejects --version under a subcommand: %j', async (args) => {
    const result = await runCliCapture(args)

    expect(result.exitCode).toBe(1)
    expect(readErrorCode(result)).toBe('USAGE_ERROR')
    expect(result.stdout).not.toContain('0.1.0')
  })

  it('reports a missing subcommand as a usage error envelope', async () => {
    const result = await runCliCapture(['workflow'])

    expect(result.exitCode).toBe(1)
    expect(readErrorCode(result)).toBe('USAGE_ERROR')
  })

  it('reports a missing argument as a usage error envelope', async () => {
    const result = await runCliCapture(['workflow', 'run'])

    expect(result.exitCode).toBe(1)
    expect(readErrorCode(result)).toBe('USAGE_ERROR')
  })
})
