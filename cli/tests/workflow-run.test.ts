import { afterEach, describe, expect, it } from 'vitest'

import {
  parseStdoutJson,
  readErrorCode,
  runCliCapture,
  startMockApi,
  type MockApi,
  type MockReply,
} from './support/cli-harness.js'

const WORKFLOW_ID = '00000000-0000-0000-0000-0000000000f1'
const EXECUTION_ID = '00000000-0000-0000-0000-0000000000e1'

const openApis: MockApi[] = []

afterEach(async () => {
  await Promise.all(openApis.splice(0).map((api) => api.close()))
})

function execution(
  overrides: Record<string, unknown>,
): Record<string, unknown> {
  return {
    execution_id: EXECUTION_ID,
    workflow_definition_id: WORKFLOW_ID,
    workflow_version: 1,
    status: 'paused',
    current_step_id: 'review',
    error_summary: null,
    ...overrides,
  }
}

async function runWorkflowAgainst(executeReply: MockReply) {
  const api = await startMockApi({
    'GET /api/v1/workflows': () => ({
      body: { items: [{ workflow_id: WORKFLOW_ID, workflow_slug: 'demo' }] },
    }),
    [`POST /api/v1/workflows/${WORKFLOW_ID}/execute`]: () => executeReply,
  })
  openApis.push(api)
  return runCliCapture(['--base-url', api.url, 'workflow', 'run', 'demo'])
}

describe('workflow run exit codes', () => {
  it('exits 0 and prints the execution when the run reaches review', async () => {
    const result = await runWorkflowAgainst({
      status: 202,
      body: execution({}),
    })

    expect(result.exitCode).toBe(0)
    expect(parseStdoutJson(result)).toMatchObject({
      execution_id: EXECUTION_ID,
      status: 'paused',
    })
  })

  it('exits 1 with an error envelope when a step fails', async () => {
    const result = await runWorkflowAgainst({
      status: 202,
      body: execution({
        current_step_id: 'ingest',
        error_summary: 'Data ingest failed: Data source not found',
      }),
    })

    expect(result.exitCode).toBe(1)
    expect(readErrorCode(result)).toBe('WORKFLOW_RUN_FAILED')
    expect(parseStdoutJson(result)).toMatchObject({
      error: {
        details: {
          execution_id: EXECUTION_ID,
          status: 'paused',
          current_step_id: 'ingest',
        },
      },
    })
  })

  it('exits 1 with an error envelope when the run fails to start', async () => {
    const result = await runWorkflowAgainst({
      status: 400,
      body: { detail: 'No active task schema available' },
    })

    expect(result.exitCode).toBe(1)
    expect(readErrorCode(result)).toBe('HTTP_400')
  })
})
