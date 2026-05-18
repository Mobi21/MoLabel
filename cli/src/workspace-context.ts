import { readFile, readdir, stat } from 'node:fs/promises'
import { basename, dirname, join, resolve } from 'node:path'

import { parse as parseYaml } from 'yaml'

import type { ArtifactResolution, WorkspaceDetection } from './types.js'

const MANIFEST_FILENAME = 'workbench.project.yaml'

const VERSIONED_KINDS = new Map([
  ['workflow', { directory: 'workbench/workflows', extension: '.yaml' }],
  ['prompt', { directory: 'workbench/prompts', extension: '.yaml' }],
  [
    'task-schema',
    { directory: 'workbench/config/task-schemas', extension: '.yaml' },
  ],
  ['mapping', { directory: 'workbench/config/mappings', extension: '.yaml' }],
])

const FILE_KINDS = new Map([
  ['workspace', MANIFEST_FILENAME],
  ['snapshot', 'workbench/snapshots'],
  ['export', 'workbench/exports'],
  ['report', 'workbench/reports'],
  ['run', 'workbench/runs'],
])

export async function detectWorkspace(
  startDir = process.cwd(),
): Promise<WorkspaceDetection> {
  let current = resolve(startDir)

  for (;;) {
    const manifestPath = join(current, MANIFEST_FILENAME)
    try {
      const raw = await readFile(manifestPath, 'utf8')
      const parsed = parseYaml(raw) as { workspace_name?: string } | null
      return {
        found: true,
        rootDir: current,
        manifestPath,
        workbenchDir: join(current, 'workbench'),
        workspaceName: parsed?.workspace_name ?? basename(current),
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
        throw error
      }
    }

    const parent = dirname(current)
    if (parent === current) {
      return {
        found: false,
        rootDir: null,
        manifestPath: null,
        workbenchDir: null,
        workspaceName: null,
      }
    }
    current = parent
  }
}

export async function resolveArtifact(
  rootDir: string,
  kind: string,
  selector: string,
): Promise<ArtifactResolution> {
  const normalizedRoot = resolve(rootDir)

  if (kind === 'workspace') {
    const path = join(normalizedRoot, MANIFEST_FILENAME)
    return {
      kind,
      selector,
      path,
      exists: await exists(path),
    }
  }

  const versioned = VERSIONED_KINDS.get(kind)
  if (versioned) {
    const path = await resolveVersionedArtifact(
      normalizedRoot,
      versioned.directory,
      selector,
      versioned.extension,
    )
    return { kind, selector, path, exists: await exists(path) }
  }

  const fixed = FILE_KINDS.get(kind)
  if (fixed) {
    const path = join(normalizedRoot, fixed, selector)
    return { kind, selector, path, exists: await exists(path) }
  }

  throw new Error(`Unknown artifact kind: ${kind}`)
}

async function resolveVersionedArtifact(
  rootDir: string,
  directory: string,
  selector: string,
  extension: string,
): Promise<string> {
  const fullDirectory = join(rootDir, directory)
  const exactPath = selector.endsWith(extension)
    ? join(fullDirectory, selector)
    : join(fullDirectory, `${selector}${extension}`)
  if (await exists(exactPath)) {
    return exactPath
  }

  const entries = await readdir(fullDirectory, { withFileTypes: true }).catch(
    () => [],
  )
  const candidates = entries
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .filter((name) => name.startsWith(selector))
    .filter((name) => name.endsWith(extension))
    .map((name) => join(fullDirectory, name))

  if (candidates.length === 0) {
    return exactPath
  }

  if (candidates.length === 1) {
    return candidates[0] ?? exactPath
  }

  const sorted = [...candidates].sort((a, b) => {
    const aBase = basename(a)
    const bBase = basename(b)
    return bBase.localeCompare(aBase, undefined, { numeric: true })
  })
  return sorted[0] ?? exactPath
}

export function normalizeArtifactSelector(selector: string): string {
  return selector.trim().replace(/\\/g, '/')
}

async function exists(path: string): Promise<boolean> {
  try {
    await stat(path)
    return true
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
      return false
    }
    return false
  }
}
