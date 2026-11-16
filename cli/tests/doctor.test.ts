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

  it('reports no providers when no backend is configured', async () => {
    const result = await runCliCapture(['doctor'])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toMatchObject({
      backend: { configured: false },
      providers: null,
    })
  })
})
