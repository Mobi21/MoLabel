import { afterEach, describe, expect, it } from 'vitest'

import { COMMAND_MANIFEST } from '../src/manifest/commands.js'
import {
  parseStdoutJson,
  runCliCapture,
  startMockApi,
  type MockApi,
} from './support/cli-harness.js'

const openApis: MockApi[] = []

afterEach(async () => {
  await Promise.all(openApis.splice(0).map((api) => api.close()))
})

describe('queue close-copies', () => {
  it('closes the unclaimed copies of the queue and prints the counts', async () => {
    const closed = { queue_id: 'q 1', closed: 6, claimed: 1 }
    const api = await startMockApi({
      'POST /api/v1/queues/q%201/close-copies': () => ({ body: closed }),
    })
    openApis.push(api)

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'queue',
      'close-copies',
      'q 1',
    ])

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toEqual(closed)
    expect(api.requests.map((r) => `${r.method} ${r.path}`)).toEqual([
      'POST /api/v1/queues/q%201/close-copies',
    ])
  })

  it('is listed in the command manifest', () => {
    expect(COMMAND_MANIFEST.commands.map((c) => c.name)).toContain(
      'queue close-copies',
    )
  })
})
