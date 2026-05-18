import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { Command } from 'commander'

import { emit } from '../output.js'
import { installSkillBundle } from '../skills.js'
import type { CliRuntimeOptions } from '../types.js'
import {
  getDefaultSkillTarget,
  getRuntimeOptions,
  outputMode,
} from './context.js'

export function registerSkillCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const skill = program.command('skill').description('Skill operations')
  skill
    .command('install')
    .description('Install the bundled skill package')
    .option('--target <path>')
    .option('--flavor <name>', 'codex or claude-code', 'codex')
    .action(async function (this: Command) {
      const commandOptions = this.opts<{ target?: string; flavor?: string }>()
      await runSkillInstall(
        getRuntimeOptions(program, runtime),
        commandOptions.target,
        commandOptions.flavor ?? 'codex',
      )
    })
}

async function runSkillInstall(
  options: CliRuntimeOptions,
  target?: string,
  flavor: string = 'codex',
): Promise<void> {
  if (flavor !== 'codex' && flavor !== 'claude-code') {
    throw new Error('skill flavor must be codex or claude-code')
  }

  const packageRoot = dirname(fileURLToPath(import.meta.url))
  const root = resolve(packageRoot, '..', '..')
  const targetRoot = resolve(target ?? getDefaultSkillTarget())
  const result = await installSkillBundle(root, targetRoot, flavor)
  await emit(result, outputMode(options))
}
