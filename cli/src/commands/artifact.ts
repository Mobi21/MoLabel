import { resolve } from 'node:path'

import type { Command } from 'commander'

import { atomicWriteTextFile, readTextFile, sha256 } from '../artifacts/io.js'
import { readInputText } from '../artifacts/input.js'
import { diffText } from '../artifacts/diff.js'
import { emit } from '../output.js'
import type { CliRuntimeOptions } from '../types.js'
import {
  buildClient,
  detectWorkspaceRoot,
  getRuntimeOptions,
  normalizeArtifactKindForApi,
  normalizeArtifactSelector,
  outputMode,
  resolveArtifactPath,
  safePostJson,
  safeReadText,
} from './context.js'

export function registerArtifactCommands(program: Command, runtime: CliRuntimeOptions): void {
  const artifact = program.command('artifact').description('Artifact operations')
  artifact
    .command('read <kind> <selector>')
    .description('Read a canonical artifact')
    .option('--raw', 'emit raw file content')
    .action(async function (this: Command, kind: string, selector: string) {
      const commandOptions = this.opts<{ raw?: boolean }>()
      await runArtifactRead(
        getRuntimeOptions(program, runtime),
        kind,
        selector,
        commandOptions.raw ?? false,
      )
    })
  artifact
    .command('diff <kind> <selector>')
    .description('Compare a canonical artifact to a candidate')
    .option('--candidate-file <path>')
    .option('--candidate-text <text>')
    .action(async function (this: Command, kind: string, selector: string) {
      const commandOptions = this.opts<{
        candidateFile?: string
        candidateText?: string
      }>()
      await runArtifactDiff(
        getRuntimeOptions(program, runtime),
        kind,
        selector,
        commandOptions.candidateFile,
        commandOptions.candidateText,
      )
    })
  artifact
    .command('write <kind> <selector>')
    .description('Write a canonical artifact safely')
    .option('--content-file <path>')
    .option('--content-text <text>')
    .option('--expected-hash <hash>')
    .action(async function (this: Command, kind: string, selector: string) {
      const commandOptions = this.opts<{
        contentFile?: string
        contentText?: string
        expectedHash?: string
      }>()
      await runArtifactWrite(
        getRuntimeOptions(program, runtime),
        kind,
        selector,
        commandOptions.contentFile,
        commandOptions.contentText,
        commandOptions.expectedHash,
      )
    })
}

async function runArtifactRead(
  options: CliRuntimeOptions,
  kind: string,
  selector: string,
  raw = false,
): Promise<void> {
  const workspace = await detectWorkspaceRoot(options.workspaceRoot)
  if (!workspace.rootDir) {
    throw new Error('No MoLabel workspace detected')
  }

  const client = await buildClient(options)
  if (client) {
    const response = await safePostJson<Record<string, unknown>>(
      client,
      '/api/v1/cli/artifacts/read',
      {
        kind: normalizeArtifactKindForApi(kind),
        selector: normalizeArtifactSelector(selector),
        workspace_root: workspace.rootDir,
      },
    )
    if (response) {
      if (raw && typeof response.content === 'string') {
        await emit(response.content, 'raw')
        return
      }
      await emit(response, outputMode(options))
      return
    }
  }

  const resolved = await resolveArtifactPath(
    workspace.rootDir,
    kind,
    normalizeArtifactSelector(selector),
  )
  const content = await readTextFile(resolved.path)
  if (raw) {
    await emit(content, 'raw')
    return
  }

  await emit(
    {
      ...resolved,
      content,
      hash: sha256(content),
    },
    outputMode(options),
  )
}

async function runArtifactDiff(
  options: CliRuntimeOptions,
  kind: string,
  selector: string,
  candidateFile?: string,
  candidateText?: string,
): Promise<void> {
  const workspace = await detectWorkspaceRoot(options.workspaceRoot)
  if (!workspace.rootDir) {
    throw new Error('No MoLabel workspace detected')
  }

  const resolved = await resolveArtifactPath(
    workspace.rootDir,
    kind,
    normalizeArtifactSelector(selector),
  )
  const current = await readTextFile(resolved.path)
  const candidate = await readInputText({
    file: candidateFile ? resolve(candidateFile) : undefined,
    text: candidateText,
    allowStdin: true,
    errorMessage: 'artifact diff requires --candidate-file, --candidate-text, or piped stdin',
  })

  const client = await buildClient(options)
  if (client) {
    const response = await safePostJson<Record<string, unknown>>(
      client,
      '/api/v1/cli/artifacts/diff',
      {
        kind: normalizeArtifactKindForApi(kind),
        selector: normalizeArtifactSelector(selector),
        content: candidate,
        workspace_root: workspace.rootDir,
      },
    )
    if (response) {
      await emit(response, outputMode(options))
      return
    }
  }
  const result = diffText(current, candidate, resolved.path)
  await emit({ ...result, selector, kind }, outputMode(options))
}

async function runArtifactWrite(
  options: CliRuntimeOptions,
  kind: string,
  selector: string,
  contentFile?: string,
  contentText?: string,
  expectedHash?: string,
): Promise<void> {
  const workspace = await detectWorkspaceRoot(options.workspaceRoot)
  if (!workspace.rootDir) {
    throw new Error('No MoLabel workspace detected')
  }

  const resolved = await resolveArtifactPath(
    workspace.rootDir,
    kind,
    normalizeArtifactSelector(selector),
  )
  const content = await readInputText({
    file: contentFile ? resolve(contentFile) : undefined,
    text: contentText,
    allowStdin: true,
    errorMessage: 'artifact write requires --content-file, --content-text, or piped stdin',
  })

  const client = await buildClient(options)
  if (client) {
    const response = await safePostJson<Record<string, unknown>>(
      client,
      '/api/v1/cli/artifacts/write',
      {
        kind: normalizeArtifactKindForApi(kind),
        selector: normalizeArtifactSelector(selector),
        content,
        expected_hash: expectedHash,
        workspace_root: workspace.rootDir,
      },
    )
    if (response) {
      await emit(response, outputMode(options))
      return
    }
  }

  const current = await safeReadText(resolved.path)
  const currentHash = current ? sha256(current) : null
  if (expectedHash && currentHash && expectedHash !== currentHash) {
    throw new Error(`expected hash mismatch for ${resolved.path}`)
  }

  await atomicWriteTextFile(resolved.path, content)
  await emit(
    {
      path: resolved.path,
      hash: sha256(content),
      selector,
      kind,
      expectedHash: expectedHash ?? null,
    },
    outputMode(options),
  )
}
