import { readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const REPO = resolve(
  fileURLToPath(new URL('.', import.meta.url)),
  '..',
  '..',
)
export const API_PORT = Number(process.env.MOLABEL_E2E_API_PORT ?? 8765)
export const WEB_PORT = Number(process.env.MOLABEL_E2E_WEB_PORT ?? 4173)
export const API_URL = `http://127.0.0.1:${String(API_PORT)}`
export const WEB_URL = `http://127.0.0.1:${String(WEB_PORT)}`

/** The run's temp folder; playwright.config.ts creates it once per run. */
export function e2eRoot(): string {
  const root = process.env.MOLABEL_E2E_ROOT
  if (!root) throw new Error('MOLABEL_E2E_ROOT is not set')
  return root
}

export interface Seed {
  workspaceId: string
  reviewers: { first: string; second: string }
  queues: { overlap: string; blind: string }
  /** The offline provider's proposal for each ticket, by external id. */
  proposals: Record<string, { intent: string; urgent: boolean }>
}

export function seedPath(): string {
  return join(e2eRoot(), 'seed.json')
}

export function readSeed(): Seed {
  return JSON.parse(readFileSync(seedPath(), 'utf8')) as Seed
}
