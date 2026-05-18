import type { Command } from 'commander'

import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import {
  buildClient,
  getRuntimeOptions,
  outputMode,
  resolveWorkspaceId,
} from './context.js'

interface AuditOptions {
  workspaceId?: string
  eventType?: string
  actor?: string
  objectType?: string
  objectId?: string
}

export function registerAuditCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const audit = program.command('audit').description('Audit operations')

  audit
    .command('timeline')
    .description('Show the workspace audit timeline')
    .option('--workspace-id <id>', 'Workspace ID')
    .option('--event-type <type>', 'Event type filter')
    .option('--actor <id>', 'Actor filter')
    .option('--object-type <type>', 'Object type filter')
    .option('--object-id <id>', 'Object ID filter')
    .action(async function (this: Command) {
      await runAuditTimeline(
        getRuntimeOptions(program, runtime),
        this.opts<AuditOptions>(),
      )
    })

  audit
    .command('explain <recordId>')
    .description('Explain audit events related to a record')
    .option('--workspace-id <id>', 'Workspace ID')
    .action(async function (this: Command, recordId: string) {
      const commandOptions = this.opts<AuditOptions>()
      await runAuditTimeline(getRuntimeOptions(program, runtime), {
        ...commandOptions,
        objectId: recordId,
      })
    })
}

async function runAuditTimeline(
  options: CliRuntimeOptions,
  query: AuditOptions,
): Promise<void> {
  const client = await requireBackendClient(options, 'audit timeline')
  const workspaceId = await resolveWorkspaceId(options, query.workspaceId)
  const response = await client.getJson(
    `/api/v1/audit${buildQuery({
      workspace_id: workspaceId,
      event_type: query.eventType,
      actor: query.actor,
      object_type: query.objectType,
      object_id: query.objectId,
    })}`,
  )
  await emit(response, outputMode(options))
}

function buildQuery(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value?.trim()) {
      search.set(key, value.trim())
    }
  }
  const query = search.toString()
  return query ? `?${query}` : ''
}

async function requireBackendClient(
  options: CliRuntimeOptions,
  commandName: string,
): Promise<NonNullable<Awaited<ReturnType<typeof buildClient>>>> {
  const client = await buildClient(options)
  if (!client) {
    throw new Error(`${commandName} requires --base-url or MOLABEL_BASE_URL`)
  }
  return client
}
