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

async function mockApi(routes: Parameters<typeof startMockApi>[0]) {
  const api = await startMockApi(routes)
  openApis.push(api)
  return api
}

const SET = '/api/v1/gold-sets/ticket-gold'

describe('gold', () => {
  it('creates a set for a task schema', async () => {
    const created = { gold_set_id: 'ticket-gold', version: 1, item_count: 0 }
    const api = await mockApi({
      'POST /api/v1/gold-sets': () => ({ status: 201, body: created }),
    })

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'gold',
      'create',
      'ticket-gold',
      '--task-schema',
      'ticket-triage',
      '--name',
      'Ticket gold',
    ])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toEqual(created)
    expect(api.requests.map((r) => r.body)).toEqual([
      {
        gold_set_id: 'ticket-gold',
        task_schema_id: 'ticket-triage',
        name: 'Ticket gold',
      },
    ])
  })

  it('promotes named records of a queue, single reviewers allowed', async () => {
    const report = { written: true, counts: { added: 2 } }
    const api = await mockApi({
      [`POST ${SET}/promote`]: () => ({ body: report }),
    })

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'gold',
      'promote',
      'ticket-gold',
      '--queue',
      'q1',
      '--record',
      'r1',
      '--record',
      'r2',
      '--allow-single-reviewer',
    ])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toEqual(report)
    expect(api.requests.map((r) => r.body)).toEqual([
      {
        queue_id: 'q1',
        record_ids: ['r1', 'r2'],
        allow_single_reviewer: true,
      },
    ])
  })

  it('appends the failures of a workflow execution', async () => {
    const api = await mockApi({
      [`POST ${SET}/append`]: () => ({ body: { counts: { added: 1 } } }),
    })

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'gold',
      'append',
      'ticket-gold',
      '--execution',
      'e1',
    ])

    expect(result.exitCode).toBe(0)
    expect(api.requests.map((r) => r.body)).toEqual([
      { workflow_execution_id: 'e1', allow_single_reviewer: false },
    ])
  })

  it.each([
    [['--queue', 'q1', '--execution', 'e1']],
    [[]],
    [['--execution', 'e1', '--record', 'r1']],
  ])(
    'refuses promote with %j before calling the backend',
    async (flags: string[]) => {
      const api = await mockApi({})

      const result = await runCliCapture([
        '--base-url',
        api.url,
        'gold',
        'promote',
        'ticket-gold',
        ...flags,
      ])

      expect(result.exitCode).toBe(1)
      expect(readErrorCode(result)).toBe('USAGE_ERROR')
      expect(api.requests).toEqual([])
    },
  )

  it('dedupes a set', async () => {
    const api = await mockApi({
      [`POST ${SET}/dedupe`]: () => ({ body: { removed: [], conflicts: [] } }),
    })

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'gold',
      'dedupe',
      'ticket-gold',
    ])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toEqual({ removed: [], conflicts: [] })
  })

  it('exports JSONL inside the JSON result by default', async () => {
    const exported = {
      gold_set_id: 'ticket-gold',
      format: 'jsonl',
      content: '{"item_id": "a"}\n',
    }
    const api = await mockApi({
      [`GET ${SET}/export`]: () => ({ body: exported }),
    })

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'gold',
      'export',
      'ticket-gold',
    ])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toEqual(exported)
    expect(api.requests[0]?.query.get('format')).toBe('jsonl')
  })

  it('exports plain JSONL lines with --raw', async () => {
    const api = await mockApi({
      [`GET ${SET}/export`]: () => ({
        body: { content: '{"item_id": "a"}\n{"item_id": "b"}\n' },
      }),
    })

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'gold',
      'export',
      'ticket-gold',
      '--raw',
    ])

    expect(result.exitCode).toBe(0)
    expect(result.stdout).toBe('{"item_id": "a"}\n{"item_id": "b"}\n')
  })

  it('exports to a path in the workspace through the backend', async () => {
    const written = { path: 'exports/gold.jsonl', item_count: 2 }
    const api = await mockApi({
      [`POST ${SET}/export`]: () => ({ body: written }),
    })

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'gold',
      'export',
      'ticket-gold',
      '--out',
      'exports/gold.jsonl',
      '--overwrite',
    ])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toEqual(written)
    expect(api.requests.map((r) => r.body)).toEqual([
      { format: 'jsonl', path: 'exports/gold.jsonl', overwrite: true },
    ])
  })

  it('reports a set of another workspace as HTTP_404 with the backend code', async () => {
    const missing = {
      error: {
        code: 'GOLD_SET_NOT_FOUND',
        message: "No gold set 'ticket-gold' in this workspace",
      },
    }
    const api = await mockApi({
      [`GET ${SET}`]: () => ({ status: 404, body: missing }),
    })

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'gold',
      'show',
      'ticket-gold',
    ])

    expect(result.exitCode).toBe(1)
    expect(parseStdoutJson(result)).toEqual({
      error: {
        code: 'HTTP_404',
        message: missing.error.message,
        details: missing,
      },
    })
  })

  it('lists every gold command in the manifest', () => {
    const names = COMMAND_MANIFEST.commands.map((command) => command.name)
    for (const name of [
      'gold list',
      'gold create',
      'gold show',
      'gold promote',
      'gold append',
      'gold dedupe',
      'gold export',
    ]) {
      expect(names).toContain(name)
    }
  })
})
