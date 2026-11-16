import { describe, expect, it } from 'vitest'

import {
  parseStdoutJson,
  readErrorCode,
  runCliCapture,
} from './support/cli-harness.js'

describe('JSON contract', () => {
  it.each([
    ['session', 'whoami'],
    ['queue', 'list'],
    ['workflow', 'run', 'wf'],
  ])(
    '%s %s fails with NO_BACKEND when no backend is configured',
    async (...command: string[]) => {
      const result = await runCliCapture(command)

      expect(result.exitCode).toBe(1)
      expect(readErrorCode(result)).toBe('NO_BACKEND')
      expect(parseStdoutJson(result)).toMatchObject({
        error: { message: expect.stringContaining('--base-url') as unknown },
      })
    },
  )
})
