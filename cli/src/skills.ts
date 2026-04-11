import { cp, mkdir, readdir } from 'node:fs/promises'
import { join, resolve } from 'node:path'

export interface InstalledSkillBundle {
  targetDir: string
  flavor: string
  files: string[]
}

export async function installSkillBundle(
  packageRoot: string,
  targetRoot: string,
  flavor: 'codex' | 'claude-code',
): Promise<InstalledSkillBundle> {
  const sourceRoot = join(packageRoot, 'skills')
  const flavorDir = join(sourceRoot, flavor)
  const sharedDir = join(sourceRoot, 'shared')
  const targetDir = resolve(targetRoot, 'molabel-cli')

  await mkdir(targetDir, { recursive: true })

  const files: string[] = []
  await copyDirectory(sharedDir, join(targetDir, 'shared'), files)
  await copyDirectory(flavorDir, targetDir, files)
  await copyStandaloneSkills(sourceRoot, targetRoot, files)

  return {
    targetDir,
    flavor,
    files,
  }
}

async function copyStandaloneSkills(
  sourceRoot: string,
  targetRoot: string,
  files: string[],
): Promise<void> {
  const entries = await readdir(sourceRoot, { withFileTypes: true })
  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue
    }
    if (
      entry.name === 'shared' ||
      entry.name === 'codex' ||
      entry.name === 'claude-code'
    ) {
      continue
    }
    await copyDirectory(
      join(sourceRoot, entry.name),
      resolve(targetRoot, entry.name),
      files,
    )
  }
}

async function copyDirectory(
  source: string,
  destination: string,
  files: string[],
): Promise<void> {
  await mkdir(destination, { recursive: true })
  const entries = await readdir(source, { withFileTypes: true })

  for (const entry of entries) {
    const sourcePath = join(source, entry.name)
    const destinationPath = join(destination, entry.name)
    if (entry.isDirectory()) {
      await copyDirectory(sourcePath, destinationPath, files)
      continue
    }
    await cp(sourcePath, destinationPath)
    files.push(destinationPath)
  }
}
