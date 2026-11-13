import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import { runCli } from '../src/cli.js'

const tempDirs: string[] = []

afterEach(async () => {
  const dirs = tempDirs.splice(0)
  await Promise.all(dirs.map((dir) => rm(dir, { recursive: true, force: true })))
})

async function captureCliJson(
  argv: string[],
): Promise<{ exitCode: number; json: unknown }> {
  const chunks: string[] = []
  const originalWrite = process.stdout.write.bind(process.stdout)
  process.stdout.write = ((chunk: string | Uint8Array) => {
    chunks.push(
      typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8'),
    )
    return true
  })

  try {
    const result = await runCli(argv)
    const stdout = chunks.join('').trim()
    return {
      exitCode: result.exitCode,
      json: stdout ? (JSON.parse(stdout) as unknown) : null,
    }
  } finally {
    process.stdout.write = originalWrite
  }
}

describe('workspace proposal commands', () => {
  it('lists only semantic proposals for the requested run', async () => {
    const root = await mkdtemp(join(tmpdir(), 'molabel-workspace-cli-'))
    tempDirs.push(root)
    await mkdir(join(root, 'workbench', 'proposals', 'artifacts'), {
      recursive: true,
    })
    await writeFile(
      join(root, 'workbench.project.yaml'),
      'workspace_name: CLI Workspace\n',
    )
    await writeFile(
      join(root, 'workbench', 'proposals', 'artifacts', 'one.json'),
      JSON.stringify({
        proposal_id: 'one',
        run_id: 'run-1',
        status: 'proposed',
        selector: 'workflow-a',
      }),
    )
    await writeFile(
      join(root, 'workbench', 'proposals', 'artifacts', 'two.json'),
      JSON.stringify({
        proposal_id: 'two',
        run_id: 'run-2',
        status: 'proposed',
        selector: 'workflow-b',
      }),
    )

    const result = await captureCliJson([
      'node',
      'molabel',
      '--workspace',
      root,
      'workspace',
      'diff',
      '--run',
      'run-1',
    ])

    expect(result.exitCode).toBe(0)
    const payload = result.json as {
      run_id: string
      proposal_count: number
      proposals: Array<{ proposal_id: string }>
    }
    expect(payload.run_id).toBe('run-1')
    expect(payload.proposal_count).toBe(1)
    expect(payload.proposals[0]?.proposal_id).toBe('one')
  })
})
