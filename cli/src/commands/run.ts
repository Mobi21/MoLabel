import type { Command } from 'commander'

import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import { buildClient, getRuntimeOptions, outputMode } from './context.js'

export function registerRunCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const run = program.command('run').description('Workflow/agent run recovery')

  run
    .command('failures <runId>')
    .description('Show failure details for a run')
    .action(async (runId: string) => {
      await runFailures(getRuntimeOptions(program, runtime), runId)
    })

  run
    .command('repair-plan <runId>')
    .description('Produce a deterministic repair plan for a failed run')
    .action(async (runId: string) => {
      await runRepairPlan(getRuntimeOptions(program, runtime), runId)
    })

  run
    .command('retry <runId>')
    .description('Prepare a retry request for a failed run')
    .option('--failed-only', 'Retry only failed records')
    .action(async function (this: Command, runId: string) {
      await runRetry(
        getRuntimeOptions(program, runtime),
        runId,
        this.opts<{ failedOnly?: boolean }>().failedOnly ?? false,
      )
    })
}

async function runFailures(
  options: CliRuntimeOptions,
  runId: string,
): Promise<void> {
  const detail = await fetchRunDetail(options, runId, 'run failures')
  const envelope = readRecord(detail.failure_envelope)
  await emit(
    {
      run_id: runId,
      status: detail.status ?? null,
      records_failed: detail.records_failed ?? 0,
      error: detail.error ?? null,
      partial_failure_summary: detail.partial_failure_summary ?? null,
      failure_envelope: envelope,
      retryable:
        typeof envelope?.retryable === 'boolean'
          ? envelope.retryable
          : Boolean(detail.error ?? detail.partial_failure_summary),
    },
    outputMode(options),
  )
}

async function runRepairPlan(
  options: CliRuntimeOptions,
  runId: string,
): Promise<void> {
  const detail = await fetchRunDetail(options, runId, 'run repair-plan')
  const envelope = readRecord(detail.failure_envelope)
  const hasFailure = Boolean(
    detail.error ?? detail.partial_failure_summary ?? envelope,
  )
  const recommended = Array.isArray(envelope?.recommended_repair_commands)
    ? envelope.recommended_repair_commands.filter(
        (value): value is string => typeof value === 'string',
      )
    : [
        `molabel run failures ${runId}`,
        `molabel run retry ${runId} --failed-only`,
      ]
  await emit(
    {
      run_id: runId,
      status: detail.status ?? null,
      failure_detected: hasFailure,
      failure_envelope: envelope,
      recommended_commands: hasFailure ? recommended : [],
      notes: hasFailure
        ? 'Inspect provider/auth/schema errors before retrying failed records.'
        : 'No failure fields were present on this run detail.',
    },
    outputMode(options),
  )
}

async function runRetry(
  options: CliRuntimeOptions,
  runId: string,
  failedOnly: boolean,
): Promise<void> {
  const detail = await fetchRunDetail(options, runId, 'run retry')
  await emit(
    {
      retry_of: runId,
      failed_only: failedOnly,
      request_body: {
        workspace_id: detail.workspace_id,
        dataset_id: detail.dataset_id,
        agent_role: detail.agent_role,
        task_schema_id: detail.task_schema_id,
        model_profile_id: detail.model_profile_id,
        runtime_profile_id: detail.runtime_profile_id ?? undefined,
        prompt_version: detail.prompt_version,
        params: {
          retry_of: runId,
          failed_only: failedOnly,
        },
      },
    },
    outputMode(options),
  )
}

async function fetchRunDetail(
  options: CliRuntimeOptions,
  runId: string,
  commandName: string,
): Promise<Record<string, unknown>> {
  const client = await buildClient(options)
  if (!client) {
    throw new Error(`${commandName} requires --base-url or MOLABEL_BASE_URL`)
  }
  return client.getJson<Record<string, unknown>>(`/api/v1/agent-runs/${runId}`)
}

function readRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return null
}
