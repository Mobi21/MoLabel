import { writeFile } from 'node:fs/promises'

import type { OutputMode } from './types.js'

export function emit(value: unknown, mode: OutputMode): Promise<void> {
  if (mode === 'raw' && typeof value === 'string') {
    process.stdout.write(value)
    return Promise.resolve()
  }

  if (mode === 'text') {
    process.stdout.write(`${formatText(value)}\n`)
    return Promise.resolve()
  }

  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`)
  return Promise.resolve()
}

export async function emitToFile(path: string, value: unknown): Promise<void> {
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, 'utf8')
}

function formatText(value: unknown): string {
  if (value === null || value === undefined) {
    return ''
  }
  if (typeof value === 'string') {
    return value
  }
  if (
    typeof value === 'number' ||
    typeof value === 'boolean' ||
    typeof value === 'bigint'
  ) {
    return String(value)
  }
  return JSON.stringify(value, null, 2)
}
