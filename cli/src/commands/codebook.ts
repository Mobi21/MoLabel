import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import type { Command } from 'commander'
import { parse as parseYaml } from 'yaml'

import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import { detectWorkspaceRoot, getRuntimeOptions, outputMode } from './context.js'

interface CodebookTestOptions {
  file?: string
}

export function registerCodebookCommands(
  program: Command,
  runtime: CliRuntimeOptions,
): void {
  const codebook = program.command('codebook').description('Codebook operations')

  codebook
    .command('test <codebookId>')
    .description('Validate a local codebook artifact')
    .option('--file <path>', 'Explicit codebook YAML/JSON path')
    .action(async function (this: Command, codebookId: string) {
      await runCodebookTest(
        getRuntimeOptions(program, runtime),
        codebookId,
        this.opts<CodebookTestOptions>(),
      )
    })
}

async function runCodebookTest(
  options: CliRuntimeOptions,
  codebookId: string,
  commandOptions: CodebookTestOptions,
): Promise<void> {
  const workspace = await detectWorkspaceRoot(options.workspaceRoot)
  if (!workspace.rootDir && !commandOptions.file) {
    throw new Error('No MoLabel workspace detected')
  }
  const codebookPath = commandOptions.file
    ? resolve(commandOptions.file)
    : resolve(
        workspace.rootDir ?? process.cwd(),
        'workbench',
        'codebooks',
        `${codebookId}.yaml`,
      )
  const raw = await readFile(codebookPath, 'utf8')
  const parsed = parseCodebook(raw, codebookPath)
  const codes = readCodes(parsed)
  const issues: string[] = []
  if (codes.length === 0) {
    issues.push('Codebook must define at least one code.')
  }
  for (const [index, code] of codes.entries()) {
    const codeId = readString(code.id) ?? readString(code.code) ?? null
    if (!codeId) {
      issues.push(`Code at index ${String(index)} is missing id/code.`)
    }
    if (!readString(code.description) && !readString(code.definition)) {
      issues.push(
        `Code ${codeId ?? String(index)} is missing description/definition.`,
      )
    }
  }

  await emit(
    {
      codebook_id: codebookId,
      path: codebookPath,
      valid: issues.length === 0,
      code_count: codes.length,
      issues,
    },
    outputMode(options),
  )
}

function parseCodebook(raw: string, path: string): unknown {
  if (path.endsWith('.json')) {
    return JSON.parse(raw) as unknown
  }
  return parseYaml(raw) as unknown
}

function readCodes(value: unknown): Array<Record<string, unknown>> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return []
  }
  const root = value as Record<string, unknown>
  const codes = root.codes ?? root.labels ?? root.categories
  if (!Array.isArray(codes)) {
    return []
  }
  return codes.filter(
    (item): item is Record<string, unknown> =>
      Boolean(item) && typeof item === 'object' && !Array.isArray(item),
  )
}

function readString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}
