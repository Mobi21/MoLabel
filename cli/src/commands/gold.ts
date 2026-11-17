import type { Command } from 'commander'

import { CliFailure } from '../errors.js'
import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import { getRuntimeOptions, outputMode, requireClient } from './context.js'

interface SourceOptions {
  queue?: string
  execution?: string
  record?: string[]
  allowSingleReviewer?: boolean
}

interface ExportOptions {
  format: string
  out?: string
  overwrite?: boolean
}

interface GoldExport {
  content?: string | null
}

const BASE = '/api/v1/gold-sets'

function setPath(slug: string, action?: string): string {
  const path = `${BASE}/${encodeURIComponent(slug)}`
  return action ? `${path}/${action}` : path
}

function collect(value: string, previous: string[] = []): string[] {
  return [...previous, value]
}

export function registerGoldCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const gold = program
    .command('gold')
    .description(
      'Gold sets: released labels kept as gold/<slug>/ files for git',
    )

  gold
    .command('list')
    .description("List the gold sets of the session's workspace")
    .action(async () => {
      const options = getRuntimeOptions(program, runtime)
      const client = await requireClient(options, 'gold list')
      await emit(await client.getJson(BASE), outputMode(options))
    })

  gold
    .command('create <slug>')
    .description('Create an empty gold set for a task schema, at version 1')
    .requiredOption('--task-schema <id>', "The task schema's id or slug")
    .option('--name <name>', 'A display name; the slug by default')
    .action(async function (this: Command, slug: string) {
      const options = getRuntimeOptions(program, runtime)
      const client = await requireClient(options, 'gold create')
      const opts = this.opts<{ taskSchema: string; name?: string }>()
      await emit(
        await client.postJson(BASE, {
          gold_set_id: slug,
          task_schema_id: opts.taskSchema,
          ...(opts.name ? { name: opts.name } : {}),
        }),
        outputMode(options),
      )
    })

  gold
    .command('show <slug>')
    .description(
      'Show a gold set: version, item count, newest items, duplicates and conflicts',
    )
    .action(async (slug: string) => {
      const options = getRuntimeOptions(program, runtime)
      const client = await requireClient(options, 'gold show')
      await emit(await client.getJson(setPath(slug)), outputMode(options))
    })

  for (const [action, description] of [
    [
      'promote',
      'Promote the adjudicated and agreed records of a queue or workflow execution',
    ],
    [
      'append',
      'Append the reviewed records the model got wrong, deduped against the set',
    ],
  ] as const) {
    const command = gold
      .command(`${action} <slug>`)
      .description(description)
      .option('--queue <id>', 'A review queue')
      .option(
        '--execution <id>',
        'A workflow execution; every review queue it made',
      )
      .option(
        '--allow-single-reviewer',
        'Also take a record one reviewer labelled, marked single_reviewer',
      )
    if (action === 'promote') {
      command.option(
        '--record <id>',
        'Only this record of --queue; repeat for more',
        collect,
      )
    }
    command.action(async function (this: Command, slug: string) {
      const options = getRuntimeOptions(program, runtime)
      const body = sourceBody(this.opts<SourceOptions>())
      const client = await requireClient(options, `gold ${action}`)
      await emit(
        await client.postJson(setPath(slug, action), body),
        outputMode(options),
      )
    })
  }

  gold
    .command('dedupe <slug>')
    .description(
      'Remove exact repeats from a gold set and report the conflicts left in it',
    )
    .action(async (slug: string) => {
      const options = getRuntimeOptions(program, runtime)
      const client = await requireClient(options, 'gold dedupe')
      await emit(
        await client.postJson(setPath(slug, 'dedupe'), {}),
        outputMode(options),
      )
    })

  gold
    .command('export <slug>')
    .description(
      'Export a gold set as JSONL: in the JSON result, as plain lines with --raw, or to --out',
    )
    .option('--format <format>', 'jsonl, the only format today', 'jsonl')
    .option('--out <path>', 'Write to this path in the workspace')
    .option('--overwrite', 'Replace the file at --out')
    .action(async function (this: Command, slug: string) {
      const options = getRuntimeOptions(program, runtime)
      const opts = this.opts<ExportOptions>()
      const client = await requireClient(options, 'gold export')
      const mode = outputMode(options)
      if (opts.out) {
        await emit(
          await client.postJson(setPath(slug, 'export'), {
            format: opts.format,
            path: opts.out,
            overwrite: opts.overwrite === true,
          }),
          mode,
        )
        return
      }
      const query = new URLSearchParams({ format: opts.format }).toString()
      const exported = await client.getJson<GoldExport>(
        `${setPath(slug, 'export')}?${query}`,
      )
      await emit(mode === 'raw' ? (exported.content ?? '') : exported, mode)
    })
}

function sourceBody(opts: SourceOptions): Record<string, unknown> {
  if (Boolean(opts.queue) === Boolean(opts.execution)) {
    throw new CliFailure('USAGE_ERROR', 'Pass --queue <id> or --execution <id>')
  }
  if (opts.record && !opts.queue) {
    throw new CliFailure('USAGE_ERROR', '--record needs --queue')
  }
  return {
    ...(opts.queue ? { queue_id: opts.queue } : {}),
    ...(opts.execution ? { workflow_execution_id: opts.execution } : {}),
    ...(opts.record ? { record_ids: opts.record } : {}),
    allow_single_reviewer: opts.allowSingleReviewer === true,
  }
}
