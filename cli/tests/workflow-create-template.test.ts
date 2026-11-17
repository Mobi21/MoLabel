import { afterEach, describe, expect, it } from 'vitest'

import {
  readErrorCode,
  runCliCapture,
  startMockApi,
  type MockApi,
} from './support/cli-harness.js'

const WORKSPACE_ID = '00000000-0000-0000-0000-0000000000a1'
const DATASET_ID = '00000000-0000-0000-0000-0000000000d1'
const SCHEMA_ID = '00000000-0000-0000-0000-0000000000c1'

const BOUND_TEMPLATE_YAML = `name: Human-in-the-Loop Review
version: 1
steps:
- id: ingest
  type: data_ingest
  config:
    dataset_id: ${DATASET_ID}
- id: review
  type: human_review
  config:
    task_schema_id: ${SCHEMA_ID}
`

const openApis: MockApi[] = []

afterEach(async () => {
  await Promise.all(openApis.splice(0).map((api) => api.close()))
})

async function startTemplateApi(): Promise<MockApi> {
  const api = await startMockApi({
    'GET /api/v1/cli/workflow-templates/human_in_the_loop': () => ({
      body: {
        template_id: 'human_in_the_loop',
        yaml: BOUND_TEMPLATE_YAML,
        bindings: { dataset_id: DATASET_ID, task_schema_id: SCHEMA_ID },
      },
    }),
    'POST /api/v1/workflows': (request) => ({
      status: 201,
      body: { workflow_id: 'wf-1', received: request.body },
    }),
  })
  openApis.push(api)
  return api
}

describe('workflow create --template', () => {
  it('asks the API to bind the named dataset and task schema', async () => {
    const api = await startTemplateApi()

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'workflow',
      'create',
      '--template',
      'human_in_the_loop',
      '--workspace-id',
      WORKSPACE_ID,
      '--dataset',
      DATASET_ID,
      '--task-schema',
      SCHEMA_ID,
    ])

    expect(result.exitCode).toBe(0)
    const templateQuery = api.requests[0]?.query
    expect(templateQuery?.get('workspace_id')).toBe(WORKSPACE_ID)
    expect(templateQuery?.get('dataset_id')).toBe(DATASET_ID)
    expect(templateQuery?.get('task_schema_id')).toBe(SCHEMA_ID)
    const created = api.requests[1]?.body as {
      steps: Array<{ step_id: string; config: Record<string, unknown> }>
    }
    expect(created.steps).toEqual([
      expect.objectContaining({
        step_id: 'ingest',
        config: { dataset_id: DATASET_ID },
      }),
      expect.objectContaining({
        step_id: 'review',
        config: { task_schema_id: SCHEMA_ID },
      }),
    ])
  })

  it('lets the API pick the workspace defaults when no binding is named', async () => {
    const api = await startTemplateApi()

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'workflow',
      'create',
      '--template',
      'human_in_the_loop',
      '--workspace-id',
      WORKSPACE_ID,
    ])

    expect(result.exitCode).toBe(0)
    const templateQuery = api.requests[0]?.query
    expect(templateQuery?.get('workspace_id')).toBe(WORKSPACE_ID)
    expect(templateQuery?.has('dataset_id')).toBe(false)
    expect(templateQuery?.has('task_schema_id')).toBe(false)
  })

  it('reports an ambiguous binding as an error envelope', async () => {
    const api = await startMockApi({
      'GET /api/v1/cli/workflow-templates/human_in_the_loop': () => ({
        status: 400,
        body: {
          error: {
            code: 'BAD_REQUEST',
            message: 'This template needs a dataset, and the workspace has 2.',
          },
        },
      }),
    })
    openApis.push(api)

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'workflow',
      'create',
      '--template',
      'human_in_the_loop',
      '--workspace-id',
      WORKSPACE_ID,
    ])

    expect(result.exitCode).toBe(1)
    expect(readErrorCode(result)).toBe('HTTP_400')
    expect(api.requests.map((request) => request.method)).toEqual(['GET'])
  })

  it('rejects --dataset without --template', async () => {
    const result = await runCliCapture([
      '--base-url',
      'http://127.0.0.1:9',
      'workflow',
      'create',
      '--name',
      'Manual',
      '--workspace-id',
      WORKSPACE_ID,
      '--dataset',
      DATASET_ID,
    ])

    expect(result.exitCode).toBe(1)
    expect(readErrorCode(result)).toBe('USAGE_ERROR')
  })

  it.each([
    [['--provider', 'offline'], 'provider', 'offline'],
    [['--model', 'gpt-4o'], 'model', 'gpt-4o'],
  ])(
    'asks the API to bind the agent steps for %j',
    async (flags, param, value) => {
      const api = await startTemplateApi()

      const result = await runCliCapture([
        '--base-url',
        api.url,
        'workflow',
        'create',
        '--template',
        'human_in_the_loop',
        '--workspace-id',
        WORKSPACE_ID,
        ...flags,
      ])

      expect(result.exitCode).toBe(0)
      const templateQuery = api.requests[0]?.query
      expect(templateQuery?.get(param)).toBe(value)
      expect(templateQuery?.has(param === 'model' ? 'provider' : 'model')).toBe(
        false,
      )
    },
  )

  it.each([
    [['--template', 'human_in_the_loop', '--provider', 'anthropic']],
    [
      [
        '--template',
        'human_in_the_loop',
        '--provider',
        'offline',
        '--model',
        'gpt-4o',
      ],
    ],
    [['--name', 'Manual', '--provider', 'offline']],
    [['--name', 'Manual', '--model', 'gpt-4o']],
  ])('rejects %j as a usage error', async (flags) => {
    const api = await startTemplateApi()

    const result = await runCliCapture([
      '--base-url',
      api.url,
      'workflow',
      'create',
      '--workspace-id',
      WORKSPACE_ID,
      ...flags,
    ])

    expect(result.exitCode).toBe(1)
    expect(readErrorCode(result)).toBe('USAGE_ERROR')
    expect(api.requests).toEqual([])
  })
})
