import { afterEach, describe, expect, it } from 'vitest'

import { COMMAND_MANIFEST } from '../src/manifest/commands.js'
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

const BASE = '/api/v1/adjudication/queues/q%201/disagreements'

async function mockApi(routes: Parameters<typeof startMockApi>[0]) {
  const api = await startMockApi(routes)
  openApis.push(api)
  return api
}

describe('adjudication', () => {
  it('lists the disagreements of a review queue', async () => {
    const queue = { queue_id: 'q 1', items: [], total: 0, unresolved: 0 }
    const api = await mockApi({ [`GET ${BASE}`]: () => ({ body: queue }) })

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'adjudication',
      'list',
      'q 1',
    ])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toEqual(queue)
  })

  it('shows one disagreement with every reviewer label set', async () => {
    const detail = { record_id: 'r/1', reviewer_labels: [], status: 'pending' }
    const api = await mockApi({
      [`GET ${BASE}/r%2F1`]: () => ({ body: detail }),
    })

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'adjudication',
      'show',
      'q 1',
      'r/1',
    ])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toEqual(detail)
  })

  it('resolves with labels and the review events the caller read', async () => {
    const resolved = { record_id: 'r1', status: 'resolved' }
    const api = await mockApi({
      [`POST ${BASE}/r1/resolve`]: () => ({ body: resolved }),
    })

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'adjudication',
      'resolve',
      'q 1',
      'r1',
      '--review-event-ids',
      'e1,e2',
      '--resolved-labels-json',
      '{"sentiment":"neutral"}',
      '--rationale',
      'Both readings are defensible; neutral fits the codebook.',
    ])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toEqual(resolved)
    expect(api.requests.map((r) => r.body)).toEqual([
      {
        resolved_labels: { sentiment: 'neutral' },
        rationale: 'Both readings are defensible; neutral fits the codebook.',
        review_event_ids: ['e1', 'e2'],
      },
    ])
  })

  it('sends another resolution without labels', async () => {
    const api = await mockApi({
      [`POST ${BASE}/r1/resolve`]: () => ({ body: {} }),
    })

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'adjudication',
      'resolve',
      'q 1',
      'r1',
      '--review-event-ids',
      'e1, e2',
      '--resolution',
      'preserve_disagreement',
    ])

    expect(result.exitCode).toBe(0)
    expect(api.requests.map((r) => r.body)).toEqual([
      { resolution: 'preserve_disagreement', review_event_ids: ['e1', 'e2'] },
    ])
  })

  it('reports a disagreement that changed since it was read', async () => {
    const conflict = {
      error: {
        code: 'CONFLICT',
        message: 'This disagreement changed since it was read; reload it',
      },
    }
    const api = await mockApi({
      [`POST ${BASE}/r1/resolve`]: () => ({ status: 409, body: conflict }),
    })

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'adjudication',
      'resolve',
      'q 1',
      'r1',
      '--review-event-ids',
      'e1',
      '--resolved-labels-json',
      '{"sentiment":"neutral"}',
    ])

    expect(result.exitCode).toBe(1)
    expect(parseStdoutJson(result)).toEqual({
      error: {
        code: 'HTTP_409',
        message: conflict.error.message,
        details: conflict,
      },
    })
  })

  it('refuses to resolve without the review events the caller read', async () => {
    const api = await mockApi({})

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'adjudication',
      'resolve',
      'q 1',
      'r1',
      '--resolved-labels-json',
      '{"sentiment":"neutral"}',
    ])

    expect(result.exitCode).toBe(1)
    expect(readErrorCode(result)).toBe('USAGE_ERROR')
    expect(api.requests).toEqual([])
  })

  it('lists only the queue-scoped commands in the manifest', () => {
    const names = COMMAND_MANIFEST.commands
      .filter((c) => c.group === 'adjudication')
      .map((c) => c.name)

    expect(names).toEqual([
      'adjudication list',
      'adjudication show',
      'adjudication resolve',
    ])
  })
})
