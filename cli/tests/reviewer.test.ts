import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import {
  parseStdoutJson,
  readErrorCode,
  runCliCapture,
  startMockApi,
  type MockApi,
} from './support/cli-harness.js'

const openApis: MockApi[] = []

afterEach(async () => {
  await Promise.all(openApis.splice(0).map((api) => api.close()))
})

const PROFILE = {
  id: '5b1f0c1e-7a37-4c55-9a43-0f5c2d6b7e10',
  display_name: 'Second reviewer',
  avatar_color: '#4A90D9',
  is_operator: false,
  is_active: true,
  created_at: '2026-11-17T00:00:00Z',
  last_active_at: null,
  preferences: null,
  workspace_id: 'ws-1',
}

async function profileApi() {
  const api = await startMockApi({
    'POST /api/v1/reviewer-profiles': () => ({ status: 201, body: PROFILE }),
  })
  openApis.push(api)
  return api
}

describe('reviewer create', () => {
  it('creates a reviewer profile in the named workspace', async () => {
    const api = await profileApi()

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'reviewer',
      'create',
      '--display-name',
      'Second reviewer',
      '--workspace-id',
      'ws-1',
    ])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toEqual(PROFILE)
    expect(api.requests.map((r) => r.body)).toEqual([
      { display_name: 'Second reviewer', workspace_id: 'ws-1' },
    ])
  })

  it("creates it in the current workspace's id by default", async () => {
    const api = await profileApi()
    const workspace = await mkdtemp(join(tmpdir(), 'molabel-reviewer-'))
    try {
      await writeFile(
        join(workspace, 'workbench.project.yaml'),
        'workspace_id: ws-from-manifest\n',
      )

      const result = await runCliCapture([
        '--base-url',
        api.url,
        '--workspace',
        workspace,
        'reviewer',
        'create',
        '--display-name',
        'Second reviewer',
      ])

      expect(result.exitCode).toBe(0)
      expect(api.requests.map((r) => r.body)).toEqual([
        { display_name: 'Second reviewer', workspace_id: 'ws-from-manifest' },
      ])
    } finally {
      await rm(workspace, { recursive: true, force: true })
    }
  })

  it('refuses to create a reviewer without a display name', async () => {
    const api = await profileApi()

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'reviewer',
      'create',
      '--workspace-id',
      'ws-1',
    ])

    expect(result.exitCode).toBe(1)
    expect(readErrorCode(result)).toBe('USAGE_ERROR')
    expect(api.requests).toEqual([])
  })
})
