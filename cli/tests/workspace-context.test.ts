import { mkdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'

import { describe, expect, it } from 'vitest'

import { detectWorkspace, resolveArtifact } from '../src/workspace-context.js'

describe('workspace context', () => {
  it('detects a workspace by manifest file', async () => {
    const root = await mkdtemp(join(tmpdir(), 'molabel-cli-'))
    await writeFile(
      join(root, 'workbench.project.yaml'),
      'workspace_name: Example\nworkspace_id: 123\ncore_version: 0.1.0\n',
      'utf8',
    )

    const detection = await detectWorkspace(root)

    expect(detection.found).toBe(true)
    expect(detection.rootDir).toBe(root)
    expect(detection.workspaceName).toBe('Example')
  })

  it('resolves workflow artifacts by selector', async () => {
    const root = await mkdtemp(join(tmpdir(), 'molabel-cli-'))
    const dir = join(root, 'workbench', 'workflows')
    await mkdir(dir, { recursive: true })
    await writeFile(join(dir, 'sample_v2.yaml'), 'name: Sample\n', 'utf8')

    const resolved = await resolveArtifact(root, 'workflow', 'sample')

    expect(resolved.path).toBe(join(dir, 'sample_v2.yaml'))
    expect(resolved.exists).toBe(true)
  })
})
