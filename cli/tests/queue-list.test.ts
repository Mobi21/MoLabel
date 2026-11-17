import { afterEach, describe, expect, it } from 'vitest'

import {
  parseStdoutJson,
  runCliCapture,
  startMockApi,
  type MockApi,
} from './support/cli-harness.js'

const WORKSPACE_ID = '00000000-0000-0000-0000-0000000000a1'

const openApis: MockApi[] = []

afterEach(async () => {
  await Promise.all(openApis.splice(0).map((api) => api.close()))
})

describe('queue list', () => {
  it('prints the queues the API reports for the workspace', async () => {
    const queues = {
      items: [
        {
          queue_id: 'q-1',
          workspace_id: WORKSPACE_ID,
          task_schema_id: 'schema-1',
          total: 3,
          available: 3,
          claimed: 0,
          submitted: 0,
          skipped: 0,
          created_at: '2026-11-15T00:00:00+00:00',
        },
      ],
    }
    const api = await startMockApi({
      'GET /api/v1/queues': () => ({ body: queues }),
    })
    openApis.push(api)

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'queue',
      'list',
      '--workspace-id',
      WORKSPACE_ID,
    ])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toEqual(queues)
    expect(api.requests[0]?.query.get('workspace_id')).toBe(WORKSPACE_ID)
  })
})
