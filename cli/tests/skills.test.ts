import { mkdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { mkdtemp } from 'node:fs/promises'
import { tmpdir } from 'node:os'

import { describe, expect, it } from 'vitest'

import { installSkillBundle } from '../src/skills.js'

describe('skills', () => {
  it('installs the bundled skill files', async () => {
    const packageRoot = await mkdtemp(join(tmpdir(), 'molabel-cli-package-'))
    await mkdir(join(packageRoot, 'skills', 'codex'), { recursive: true })
    await mkdir(join(packageRoot, 'skills', 'shared'), { recursive: true })
    await writeFile(join(packageRoot, 'skills', 'codex', 'SKILL.md'), '# codex\n', 'utf8')
    await writeFile(join(packageRoot, 'skills', 'shared', 'AGENTS.md'), '# shared\n', 'utf8')

    const targetRoot = await mkdtemp(join(tmpdir(), 'molabel-cli-target-'))
    const result = await installSkillBundle(packageRoot, targetRoot, 'codex')

    expect(result.targetDir).toContain('molabel-cli')
    expect(result.files.length).toBeGreaterThan(0)
  })
})
