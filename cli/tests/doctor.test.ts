import { afterEach, describe, expect, it } from 'vitest'

import {
  parseStdoutJson,
  runCliCapture,
  startMockApi,
  type MockApi,
} from './support/cli-harness.js'

const OFFLINE = {
  provider_type: 'offline',
  name: 'Offline heuristic (no LLM)',
  health: { is_healthy: true },
  suggested_models: ['offline-heuristic'],
}

const openApis: MockApi[] = []

afterEach(async () => {
  await Promise.all(openApis.splice(0).map((api) => api.close()))
})

describe('doctor', () => {
  it('lists the providers the backend can use', async () => {
    const api = await startMockApi({
      'GET /health': () => ({ body: { status: 'ok' } }),
      'GET /api/v1/providers': () => ({ body: { providers: [OFFLINE] } }),
    })
    openApis.push(api)

    const result = await runCliCapture(['--base-url', api.url, 'doctor'])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toMatchObject({
      backend: { configured: true, healthy: 'ok' },
      providers: [OFFLINE],
    })
  })

  it('lists rows whose foreign keys point at missing rows', async () => {
    const dangling = { table: 'review_events', parent: 'records', rows: 2 }
    const api = await startMockApi({
      'GET /health': () => ({ body: { status: 'ok' } }),
      'GET /api/v1/cli/status': () => ({
        body: { ok: true, foreign_key_violations: [dangling] },
      }),
    })
    openApis.push(api)

    const result = await runCliCapture(['--base-url', api.url, 'doctor'])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toMatchObject({
      database: { foreign_key_violations: [dangling] },
    })
  })

  it('warns about workspaces registered outside the allowed parent folders', async () => {
    const outside = {
      workspace_id: '6f1c2b8e-0d1a-4e8f-9a51-0f0c2d3e4b5a',
      workspace_name: 'Legacy',
      root_path: '/srv/legacy',
      reason: 'outside_allowed_parents',
      message: 'Workspace Legacy: /srv/legacy is outside the allowed parents.',
    }
    const api = await startMockApi({
      'GET /health': () => ({ body: { status: 'ok' } }),
      'GET /api/v1/cli/status': () => ({
        body: { ok: true, workspace_roots_not_allowed: [outside] },
      }),
    })
    openApis.push(api)

    const result = await runCliCapture(['--base-url', api.url, 'doctor'])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toMatchObject({
      database: {
        foreign_key_violations: [],
        workspace_roots_not_allowed: [outside],
      },
    })
  })

  it('reports no providers when no backend is configured', async () => {
    const result = await runCliCapture(['doctor'])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toMatchObject({
      backend: { configured: false },
      providers: null,
      database: null,
    })
  })
})
