import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { homedir } from 'node:os'

import type { CliConfig } from './types.js'

export function getConfigDir(): string {
  const xdg = process.env.XDG_CONFIG_HOME
  if (xdg && xdg.trim()) {
    return join(xdg, 'molabel')
  }

  return join(homedir(), '.config', 'molabel')
}

export function getDefaultConfigPath(): string {
  return join(getConfigDir(), 'cli.json')
}

export async function loadConfig(
  configPath = getDefaultConfigPath(),
): Promise<CliConfig> {
  try {
    const raw = await readFile(configPath, 'utf8')
    return JSON.parse(raw) as CliConfig
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
      return {}
    }
    throw error
  }
}

export async function saveConfig(
  config: CliConfig,
  configPath = getDefaultConfigPath(),
): Promise<void> {
  await mkdir(dirname(configPath), { recursive: true })
  await writeFile(configPath, `${JSON.stringify(config, null, 2)}\n`, 'utf8')
}

export function resolveConfig(
  fileConfig: CliConfig,
  runtime: {
    baseUrl?: string
    sessionToken?: string
    workspaceRoot?: string
  },
): CliConfig {
  const result: CliConfig = {}
  const baseUrl =
    runtime.baseUrl ?? process.env.MOLABEL_BASE_URL ?? fileConfig.baseUrl
  if (baseUrl) {
    result.baseUrl = baseUrl
  }

  const sessionToken =
    runtime.sessionToken ??
    process.env.MOLABEL_SESSION ??
    fileConfig.sessionToken
  if (sessionToken) {
    result.sessionToken = sessionToken
  }

  const workspaceRoot =
    runtime.workspaceRoot ??
    process.env.MOLABEL_WORKSPACE ??
    fileConfig.workspaceRoot
  if (workspaceRoot) {
    result.workspaceRoot = workspaceRoot
  }

  return result
}
