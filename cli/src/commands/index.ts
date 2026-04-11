import type { Command } from 'commander'

import type { CliRuntimeOptions } from '../types.js'
import { registerBenchmarkCommands } from './benchmark.js'
import { registerAdjudicationCommands } from './adjudication.js'
import { registerAgentRunCommands } from './agent-run.js'
import { registerArtifactCommands } from './artifact.js'
import { registerCoreCommands } from './core.js'
import { registerDatasetCommands } from './dataset.js'
import { registerExportCommands } from './export.js'
import { registerModelProfileCommands } from './model-profile.js'
import { registerPromptCommands } from './prompt.js'
import { registerProviderCommands } from './provider.js'
import { registerQualityCommands } from './quality.js'
import { registerQueueCommands } from './queue.js'
import { registerReleaseCommands } from './release.js'
import { registerReviewCommands } from './review.js'
import { registerSessionCommands } from './session.js'
import { registerSkillCommands } from './skill.js'
import { registerTaskSchemaCommands } from './task-schema.js'
import { registerWorkflowCommands } from './workflow.js'
import { registerWorkspaceCommands } from './workspace.js'

export function registerCommands(program: Command, runtime: CliRuntimeOptions): void {
  registerCoreCommands(program, runtime)
  registerSessionCommands(program, runtime)
  registerWorkspaceCommands(program, runtime)
  registerBenchmarkCommands(program, runtime)
  registerProviderCommands(program, runtime)
  registerModelProfileCommands(program, runtime)
  registerDatasetCommands(program, runtime)
  registerTaskSchemaCommands(program, runtime)
  registerPromptCommands(program, runtime)
  registerWorkflowCommands(program, runtime)
  registerQueueCommands(program, runtime)
  registerReviewCommands(program, runtime)
  registerAdjudicationCommands(program, runtime)
  registerAgentRunCommands(program, runtime)
  registerQualityCommands(program, runtime)
  registerExportCommands(program, runtime)
  registerReleaseCommands(program, runtime)
  registerArtifactCommands(program, runtime)
  registerSkillCommands(program, runtime)
}
