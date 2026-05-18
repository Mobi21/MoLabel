import { createServer } from 'node:http'
import { readFile, mkdtemp } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'

import { parse as parseYaml } from 'yaml'
import { afterEach, describe, expect, it } from 'vitest'

import { runCli } from '../src/cli.js'

interface RecordedRequest {
  method: string
  path: string
  headers: Record<string, string | string[] | undefined>
  body: unknown
}

interface MockApiServer {
  close: () => Promise<void>
  requests: RecordedRequest[]
  url: string
}

interface ScenarioFixture {
  manifest: Record<string, unknown>
  root: string
  scenario: {
    default_model_profile: {
      model_identifier: string
      provider_name: string
      provider_type: string
      sdk_stack: string
    }
    scenario_id: string
  } & Record<string, unknown>
}

const openServers: MockApiServer[] = []

afterEach(async () => {
  await Promise.all(openServers.splice(0).map((server) => server.close()))
})

async function loadScenario(relativeRoot: string): Promise<ScenarioFixture> {
  const root = resolve(
    process.cwd(),
    '..',
    'fixtures',
    'benchmarks',
    relativeRoot,
  )
  const [manifestText, scenarioText] = await Promise.all([
    readFile(join(root, 'workbench.project.yaml'), 'utf8'),
    readFile(join(root, 'workbench', 'benchmarks', 'scenario.yaml'), 'utf8'),
  ])
  return {
    manifest: parseYaml(manifestText) as Record<string, unknown>,
    root,
    scenario: parseYaml(scenarioText) as ScenarioFixture['scenario'],
  }
}

async function captureCliJson(
  argv: string[],
): Promise<{ exitCode: number; json: unknown }> {
  const chunks: string[] = []
  const originalWrite = process.stdout.write.bind(process.stdout)
  process.stdout.write = ((chunk: string | Uint8Array) => {
    chunks.push(
      typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8'),
    )
    return true
  }) as typeof process.stdout.write

  try {
    const result = await runCli(argv)
    const stdout = chunks.join('').trim()
    return {
      exitCode: result.exitCode,
      json: stdout ? (JSON.parse(stdout) as unknown) : null,
    }
  } finally {
    process.stdout.write = originalWrite
  }
}

async function createMockApiServer(
  workspaceId: string,
): Promise<MockApiServer> {
  const requests: RecordedRequest[] = []
  const state = {
    datasetId: 'dataset-live-1',
    promptId: 'prompt-live-1',
    reviewTaskId: 'task-live-1',
    schemaId: 'schema-live-1',
    sessionToken: 'test-session-token',
    workspaceId,
  }

  const server = createServer((req, res) => {
    void (async () => {
      const url = new URL(req.url ?? '/', 'http://127.0.0.1')
      const chunks: Buffer[] = []
      for await (const chunk of req as AsyncIterable<Buffer | string>) {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
      }
      const rawBody = Buffer.concat(chunks).toString('utf8')
      const body = rawBody ? (JSON.parse(rawBody) as unknown) : null
      const method = req.method ?? 'GET'

      requests.push({
        method,
        path: url.pathname,
        headers: req.headers,
        body,
      })

      const sendJson = (
        status: number,
        payload: unknown,
        headers?: Record<string, string>,
      ) => {
        res.statusCode = status
        res.setHeader('content-type', 'application/json')
        for (const [key, value] of Object.entries(headers ?? {})) {
          res.setHeader(key, value)
        }
        res.end(JSON.stringify(payload))
      }

      if (req.method === 'GET' && url.pathname === '/health') {
        sendJson(200, { status: 'ok' })
        return
      }

      if (req.method === 'GET' && url.pathname === '/api/v1/me') {
        sendJson(200, {
          id: 'reviewer-live',
          display_name: 'CLI Benchmark Reviewer',
        })
        return
      }

      if (
        req.method === 'POST' &&
        (url.pathname === '/api/v1/sessions' ||
          url.pathname === '/api/v1/sessions/switch')
      ) {
        sendJson(
          200,
          { id: 'reviewer-live', display_name: 'CLI Benchmark Reviewer' },
          {
            'set-cookie': `molabel_session=${state.sessionToken}; Path=/; HttpOnly`,
          },
        )
        return
      }

      if (req.method === 'POST' && url.pathname === '/api/v1/datasets') {
        const datasetBody = body as Record<string, unknown>
        const datasetName =
          typeof datasetBody.dataset_name === 'string'
            ? datasetBody.dataset_name
            : 'dataset'
        sendJson(201, {
          dataset_id: state.datasetId,
          dataset_name: datasetBody.dataset_name,
          dataset_slug: datasetName.toLowerCase().replaceAll(' ', '-'),
          workspace_id: datasetBody.workspace_id,
          description: datasetBody.description ?? null,
          source_type: datasetBody.source_type,
          loader_plugin: datasetBody.loader_plugin ?? null,
          record_kind: datasetBody.record_kind ?? null,
          canonical_id_strategy:
            datasetBody.canonical_id_strategy ?? 'external_id',
          indexing_mode: datasetBody.indexing_mode ?? 'full',
          record_count: 0,
          labeled_count: 0,
          health_status: null,
          last_indexed_at: null,
          created_at: '2026-03-28T00:00:00Z',
          updated_at: '2026-03-28T00:00:00Z',
        })
        return
      }

      if (
        req.method === 'POST' &&
        url.pathname === `/api/v1/datasets/${state.datasetId}/import`
      ) {
        sendJson(202, {
          job_id: 'import-job-1',
          status: 'queued',
          dataset_id: state.datasetId,
          records_total: null,
          records_imported: null,
          records_skipped: null,
          errors: [],
          started_at: null,
          completed_at: null,
        })
        return
      }

      if (req.method === 'POST' && url.pathname === '/api/v1/task-schemas') {
        const schemaBody = body as Record<string, unknown>
        sendJson(201, {
          task_schema_id: state.schemaId,
          task_schema_slug: schemaBody.task_schema_slug ?? 'schema-live',
          version: 1,
          task_type: schemaBody.task_type,
          title: schemaBody.title,
          instructions: schemaBody.instructions ?? null,
          record_selector: schemaBody.record_selector ?? null,
          label_fields: schemaBody.label_fields ?? [],
          required_fields: schemaBody.required_fields ?? [],
          optional_fields: schemaBody.optional_fields ?? [],
          blind_review_policy:
            schemaBody.blind_review_policy ?? 'hide_agent_outputs_by_default',
          overlap_policy: schemaBody.overlap_policy ?? null,
          adjudication_policy: schemaBody.adjudication_policy ?? null,
          supported_agent_roles: schemaBody.supported_agent_roles ?? [],
          default_model_profile_id: schemaBody.default_model_profile_id ?? null,
          export_mapping: schemaBody.export_mapping ?? null,
          is_active: true,
          is_frozen: false,
          file_path: schemaBody.file_path ?? null,
          workspace_id: schemaBody.workspace_id,
          created_at: '2026-03-28T00:00:00Z',
          updated_at: '2026-03-28T00:00:00Z',
        })
        return
      }

      if (req.method === 'POST' && url.pathname === '/api/v1/prompts') {
        const promptBody = body as Record<string, unknown>
        sendJson(201, {
          prompt_id: state.promptId,
          workspace_id: promptBody.workspace_id,
          name: promptBody.name,
          agent_role: promptBody.agent_role,
          task_schema_id: promptBody.task_schema_id,
          current_version: 'v1',
          versions: [
            {
              version: 'v1',
              system_instructions: promptBody.system_instructions,
              task_rubric: promptBody.task_rubric ?? null,
              few_shot_examples: promptBody.few_shot_examples ?? [],
              correction_batch_id: null,
              content_hash: 'hash-live-1',
              is_locked: false,
              agent_run_ids: [],
              created_at: '2026-03-28T00:00:00Z',
            },
          ],
          file_path: `prompts/${state.promptId}.yaml`,
          created_at: '2026-03-28T00:00:00Z',
          updated_at: '2026-03-28T00:00:00Z',
        })
        return
      }

      if (req.method === 'POST' && url.pathname === '/api/v1/agent-runs') {
        const runBody = body as Record<string, unknown>
        sendJson(202, {
          agent_run_id: 'agent-run-live-1',
          workspace_id: runBody.workspace_id,
          dataset_id: runBody.dataset_id,
          agent_role: runBody.agent_role,
          plugin_adapter: 'benchmark.mock',
          model_profile_id: runBody.model_profile_id,
          model_identifier: 'MiniMax-M2.7-highspeed',
          runtime_profile_id: runBody.runtime_profile_id ?? null,
          prompt_version: runBody.prompt_version ?? 'v1',
          prompt_content_hash: 'hash-live-1',
          task_schema_id: runBody.task_schema_id,
          status: 'pending',
          records_targeted: 5,
          records_completed: 0,
          records_failed: 0,
          retry_count: 0,
          partial_failure_summary: null,
          comparison_id: null,
          cost: null,
          execution_params: runBody.params ?? {},
          started_at: null,
          completed_at: null,
          created_at: '2026-03-28T00:00:00Z',
          error: null,
        })
        return
      }

      if (
        req.method === 'POST' &&
        /^\/api\/v1\/queues\/[^/]+\/claim$/.test(url.pathname)
      ) {
        const queueId = url.pathname.split('/')[4]
        sendJson(200, {
          queue_empty: false,
          message: 'claimed',
          task: {
            id: state.reviewTaskId,
            queue_id: queueId,
            record_id: 'thread-003',
            task_schema_id: state.schemaId,
            status: 'claimed',
            priority: 1,
            priority_reason: 'benchmark_high_severity',
            claimed_by: 'reviewer-live',
            claimed_at: '2026-03-28T00:00:00Z',
            claim_expired_count: 0,
            is_overlap: false,
            is_calibration: false,
            draft_labels: null,
            ai_revealed: false,
            ai_revealed_at: null,
            submitted_at: null,
            created_at: '2026-03-28T00:00:00Z',
            updated_at: '2026-03-28T00:00:00Z',
            workspace_id: state.workspaceId,
            dataset_id: state.datasetId,
            agent_output: null,
            blind_review_policy: 'hide_agent_outputs_by_default',
          },
        })
        return
      }

      if (
        req.method === 'POST' &&
        url.pathname === `/api/v1/review-tasks/${state.reviewTaskId}/reveal-ai`
      ) {
        sendJson(200, {
          message: 'ai_revealed',
          task: {
            id: state.reviewTaskId,
            queue_id: 'live-review-queue',
            record_id: 'thread-003',
            task_schema_id: state.schemaId,
            status: 'claimed',
            priority: 1,
            priority_reason: 'benchmark_high_severity',
            claimed_by: 'reviewer-live',
            claimed_at: '2026-03-28T00:00:00Z',
            claim_expired_count: 0,
            is_overlap: false,
            is_calibration: false,
            draft_labels: null,
            ai_revealed: true,
            ai_revealed_at: '2026-03-28T00:01:00Z',
            submitted_at: null,
            created_at: '2026-03-28T00:00:00Z',
            updated_at: '2026-03-28T00:01:00Z',
            workspace_id: state.workspaceId,
            dataset_id: state.datasetId,
            blind_review_policy: 'hide_agent_outputs_by_default',
            agent_output: {
              id: 'agent-output-live-1',
              agent_run_id: 'agent-run-live-1',
              record_id: 'thread-003',
              task_schema_id: state.schemaId,
              output_type: 'labels',
              labels: {
                severity: 'high',
                violation_types: ['harassment'],
                allow_publish: false,
              },
              raw_response: null,
              confidence_self_reported: 0.73,
              confidence_self_consistency: 0.68,
              confidence_logprobs: null,
              composite_confidence: 0.7,
              tokens_input: 120,
              tokens_output: 40,
              latency_ms: 840,
              validation_passed: true,
              validation_errors: [],
              created_at: '2026-03-28T00:00:00Z',
              workspace_id: state.workspaceId,
            },
          },
        })
        return
      }

      if (
        req.method === 'POST' &&
        url.pathname === `/api/v1/review-tasks/${state.reviewTaskId}/submit`
      ) {
        const submitBody = body as Record<string, unknown>
        sendJson(200, {
          message: 'submitted',
          queue_empty: true,
          next_task: null,
          submitted_task: {
            id: state.reviewTaskId,
            queue_id: 'live-review-queue',
            record_id: 'thread-003',
            task_schema_id: state.schemaId,
            status: 'submitted',
            priority: 1,
            priority_reason: 'benchmark_high_severity',
            claimed_by: 'reviewer-live',
            claimed_at: '2026-03-28T00:00:00Z',
            claim_expired_count: 0,
            is_overlap: false,
            is_calibration: false,
            draft_labels: null,
            ai_revealed: true,
            ai_revealed_at: '2026-03-28T00:01:00Z',
            submitted_at: '2026-03-28T00:02:00Z',
            created_at: '2026-03-28T00:00:00Z',
            updated_at: '2026-03-28T00:02:00Z',
            workspace_id: state.workspaceId,
            dataset_id: state.datasetId,
            submitted_labels: submitBody.labels,
          },
        })
        return
      }

      sendJson(404, {
        error: {
          code: 'NOT_FOUND',
          message: `Unhandled route ${method} ${url.pathname}`,
        },
      })
    })().catch((error: unknown) => {
      res.statusCode = 500
      res.end(error instanceof Error ? error.message : 'Mock server error')
    })
  })

  await new Promise<void>((resolvePromise) => {
    server.listen(0, '127.0.0.1', () => {
      resolvePromise()
    })
  })

  const address = server.address()
  if (!address || typeof address === 'string') {
    throw new Error('Failed to bind mock server')
  }

  const mockServer: MockApiServer = {
    close: () =>
      new Promise<void>((resolvePromise, rejectPromise) => {
        server.close((error) => {
          if (error) {
            rejectPromise(error)
            return
          }
          resolvePromise()
        })
      }),
    requests,
    url: `http://127.0.0.1:${String(address.port)}`,
  }

  openServers.push(mockServer)
  return mockServer
}

describe('benchmark live cli flows', () => {
  it('drives the messy support CSV benchmark through session, dataset, import, and schema commands', async () => {
    const fixture = await loadScenario('messy-support-ops')
    const configPath = join(
      await mkdtemp(join(tmpdir(), 'molabel-cli-benchmark-')),
      'config.json',
    )
    const server = await createMockApiServer(
      String(fixture.manifest.workspace_id),
    )

    const sessionResult = await captureCliJson([
      'node',
      'molabel',
      '--base-url',
      server.url,
      '--workspace',
      fixture.root,
      '--config',
      configPath,
      '--json',
      'session',
      'select',
      'reviewer-support',
    ])
    expect(sessionResult.exitCode).toBe(0)
    expect((sessionResult.json as Record<string, unknown>).sessionToken).toBe(
      'test-session-token',
    )

    const datasetResult = await captureCliJson([
      'node',
      'molabel',
      '--workspace',
      fixture.root,
      '--config',
      configPath,
      '--json',
      'dataset',
      'create',
      '--name',
      'Messy Support Tickets',
      '--source-type',
      String(fixture.scenario.raw_format),
      '--loader-plugin',
      String(fixture.scenario.loader_plugin),
      '--record-kind',
      'text',
      '--canonical-id-strategy',
      'source_record_id',
      '--indexing-mode',
      'projection',
    ])
    expect(datasetResult.exitCode).toBe(0)
    expect((datasetResult.json as Record<string, unknown>).dataset_id).toBe(
      'dataset-live-1',
    )

    const sourcePath = join(fixture.root, String(fixture.scenario.source_path))
    const importResult = await captureCliJson([
      'node',
      'molabel',
      '--workspace',
      fixture.root,
      '--config',
      configPath,
      '--json',
      'dataset',
      'import',
      'dataset-live-1',
      '--source-uri',
      sourcePath,
      '--options-json',
      JSON.stringify({ delimiter: ',', text_field: 'ticket_body' }),
    ])
    expect(importResult.exitCode).toBe(0)

    const schemaResult = await captureCliJson([
      'node',
      'molabel',
      '--workspace',
      fixture.root,
      '--config',
      configPath,
      '--json',
      'task-schema',
      'create',
      '--file',
      join(fixture.root, String(fixture.scenario.task_schema_path)),
    ])
    expect(schemaResult.exitCode).toBe(0)
    expect((schemaResult.json as Record<string, unknown>).task_schema_id).toBe(
      'schema-live-1',
    )

    const datasetCreateRequest = server.requests.find(
      (request) =>
        request.method === 'POST' && request.path === '/api/v1/datasets',
    )
    const datasetImportRequest = server.requests.find(
      (request) =>
        request.method === 'POST' &&
        request.path === '/api/v1/datasets/dataset-live-1/import',
    )
    const taskSchemaRequest = server.requests.find(
      (request) =>
        request.method === 'POST' && request.path === '/api/v1/task-schemas',
    )

    expect(datasetCreateRequest?.headers.cookie).toContain(
      'molabel_session=test-session-token',
    )
    expect(datasetCreateRequest?.body).toMatchObject({
      workspace_id: fixture.manifest.workspace_id,
      source_type: 'csv',
      loader_plugin: 'molabel.loaders.csv',
      canonical_id_strategy: 'source_record_id',
      indexing_mode: 'projection',
    })
    expect(datasetImportRequest?.body).toMatchObject({
      source_uri: sourcePath,
      options: { delimiter: ',', text_field: 'ticket_body' },
    })
    expect(taskSchemaRequest?.body).toMatchObject({
      workspace_id: fixture.manifest.workspace_id,
      task_schema_slug: 'support-triage-v1',
      blind_review_policy: 'hide_agent_outputs_by_default',
    })
  })

  it('starts a MiniMax agent run for the claims extraction benchmark through the CLI', async () => {
    const fixture = await loadScenario('claims-audit-extraction')
    const configPath = join(
      await mkdtemp(join(tmpdir(), 'molabel-cli-benchmark-')),
      'config.json',
    )
    const server = await createMockApiServer(
      String(fixture.manifest.workspace_id),
    )

    await captureCliJson([
      'node',
      'molabel',
      '--base-url',
      server.url,
      '--workspace',
      fixture.root,
      '--config',
      configPath,
      '--json',
      'session',
      'select',
      'reviewer-claims',
    ])

    await captureCliJson([
      'node',
      'molabel',
      '--workspace',
      fixture.root,
      '--config',
      configPath,
      '--json',
      'dataset',
      'create',
      '--name',
      'Claims Packets',
      '--source-type',
      'jsonl',
      '--loader-plugin',
      'molabel.loaders.jsonl',
      '--record-kind',
      'document',
    ])

    await captureCliJson([
      'node',
      'molabel',
      '--workspace',
      fixture.root,
      '--config',
      configPath,
      '--json',
      'task-schema',
      'create',
      '--file',
      join(fixture.root, String(fixture.scenario.task_schema_path)),
    ])

    const promptResult = await captureCliJson([
      'node',
      'molabel',
      '--workspace',
      fixture.root,
      '--config',
      configPath,
      '--json',
      'prompt',
      'create',
      '--name',
      'Claims Audit Prompt v1',
      '--agent-role',
      'proposer',
      '--task-schema-id',
      'schema-live-1',
      '--system-instructions',
      'Use MiniMax 2.7 highspeed to extract routing and risk fields from noisy claim packets.',
      '--task-rubric',
      'Prefer explicit evidence from OCR text and attachment references.',
    ])
    expect(promptResult.exitCode).toBe(0)
    expect((promptResult.json as Record<string, unknown>).current_version).toBe(
      'v1',
    )

    const agentRunBody = {
      workspace_id: fixture.manifest.workspace_id,
      dataset_id: 'dataset-live-1',
      agent_role: 'proposer',
      task_schema_id: 'schema-live-1',
      model_profile_id: 'minimax-anthropic-profile',
      prompt_version: 'v1',
      params: {
        benchmark: fixture.scenario.scenario_id,
        provider_name: fixture.scenario.default_model_profile.provider_name,
        provider_type: fixture.scenario.default_model_profile.provider_type,
        model_identifier:
          fixture.scenario.default_model_profile.model_identifier,
        sdk_stack: fixture.scenario.default_model_profile.sdk_stack,
      },
    }

    const agentRunResult = await captureCliJson([
      'node',
      'molabel',
      '--workspace',
      fixture.root,
      '--config',
      configPath,
      '--json',
      'agent-run',
      'start',
      '--body-text',
      JSON.stringify(agentRunBody),
    ])
    expect(agentRunResult.exitCode).toBe(0)
    expect(
      (agentRunResult.json as Record<string, unknown>).model_identifier,
    ).toBe('MiniMax-M2.7-highspeed')

    const promptRequest = server.requests.find(
      (request) =>
        request.method === 'POST' && request.path === '/api/v1/prompts',
    )
    const agentRunRequest = server.requests.find(
      (request) =>
        request.method === 'POST' && request.path === '/api/v1/agent-runs',
    )

    expect(promptRequest?.body).toMatchObject({
      workspace_id: fixture.manifest.workspace_id,
      agent_role: 'proposer',
      task_schema_id: 'schema-live-1',
    })
    expect(agentRunRequest?.headers.cookie).toContain(
      'molabel_session=test-session-token',
    )
    expect(agentRunRequest?.body).toMatchObject({
      workspace_id: fixture.manifest.workspace_id,
      dataset_id: 'dataset-live-1',
      agent_role: 'proposer',
      task_schema_id: 'schema-live-1',
      model_profile_id: 'minimax-anthropic-profile',
      prompt_version: 'v1',
      params: {
        provider_name: 'MiniMax',
        provider_type: 'anthropic',
        model_identifier: 'MiniMax-M2.7-highspeed',
        sdk_stack: 'anthropic_sdk',
      },
    })
  })

  it('runs the markdown moderation benchmark through queue claim, AI reveal, and review submit', async () => {
    const fixture = await loadScenario('forum-policy-moderation')
    const configPath = join(
      await mkdtemp(join(tmpdir(), 'molabel-cli-benchmark-')),
      'config.json',
    )
    const server = await createMockApiServer(
      String(fixture.manifest.workspace_id),
    )

    await captureCliJson([
      'node',
      'molabel',
      '--base-url',
      server.url,
      '--workspace',
      fixture.root,
      '--config',
      configPath,
      '--json',
      'session',
      'select',
      'reviewer-policy',
    ])

    await captureCliJson([
      'node',
      'molabel',
      '--workspace',
      fixture.root,
      '--config',
      configPath,
      '--json',
      'queue',
      'claim',
      'live-review-queue',
    ])

    const revealResult = await captureCliJson([
      'node',
      'molabel',
      '--workspace',
      fixture.root,
      '--config',
      configPath,
      '--json',
      'review',
      'reveal-ai',
      'task-live-1',
    ])
    expect(revealResult.exitCode).toBe(0)
    expect(
      (
        (revealResult.json as Record<string, unknown>).task as Record<
          string,
          unknown
        >
      ).ai_revealed,
    ).toBe(true)

    const payloadPath = join(
      fixture.root,
      'workbench',
      'benchmarks',
      'payloads',
      'review-submit-labels.json',
    )
    const submitResult = await captureCliJson([
      'node',
      'molabel',
      '--workspace',
      fixture.root,
      '--config',
      configPath,
      '--json',
      'review',
      'submit',
      'task-live-1',
      '--labels-file',
      payloadPath,
      '--decision',
      'correct',
      '--rationale',
      'Escalating because the xenophobic language and harassment are explicit.',
      '--no-auto-claim-next',
    ])
    expect(submitResult.exitCode).toBe(0)
    expect((submitResult.json as Record<string, unknown>).message).toBe(
      'submitted',
    )

    const queueClaimRequest = server.requests.find(
      (request) =>
        request.method === 'POST' &&
        request.path === '/api/v1/queues/live-review-queue/claim',
    )
    const revealRequest = server.requests.find(
      (request) =>
        request.method === 'POST' &&
        request.path === '/api/v1/review-tasks/task-live-1/reveal-ai',
    )
    const submitRequest = server.requests.find(
      (request) =>
        request.method === 'POST' &&
        request.path === '/api/v1/review-tasks/task-live-1/submit',
    )

    expect(queueClaimRequest?.headers.cookie).toContain(
      'molabel_session=test-session-token',
    )
    expect(revealRequest?.headers.cookie).toContain(
      'molabel_session=test-session-token',
    )
    expect(submitRequest?.body).toMatchObject({
      decision: 'correct',
      rationale:
        'Escalating because the xenophobic language and harassment are explicit.',
      auto_claim_next: false,
      labels: {
        severity: 'critical',
        violation_types: ['hate_or_xenophobia', 'harassment'],
        allow_publish: false,
      },
    })
  })
})
