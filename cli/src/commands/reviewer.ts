import type { Command } from 'commander'

import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import {
  getRuntimeOptions,
  outputMode,
  requireClient,
  resolveWorkspaceId,
} from './context.js'

export function registerReviewerCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const reviewer = program
    .command('reviewer')
    .description('Reviewer profile operations')

  reviewer
    .command('create')
    .description('Create a reviewer profile in a workspace')
    .requiredOption('--display-name <name>', 'Name the reviewer goes by')
    .option('--workspace-id <id>', 'Workspace ID override')
    .action(async function (this: Command) {
      const options = getRuntimeOptions(program, runtime)
      const { displayName, workspaceId } = this.opts<{
        displayName: string
        workspaceId?: string
      }>()
      const client = await requireClient(options, 'reviewer create')
      await emit(
        await client.postJson('/api/v1/reviewer-profiles', {
          display_name: displayName,
          workspace_id: await resolveWorkspaceId(options, workspaceId),
        }),
        outputMode(options),
      )
    })
}
