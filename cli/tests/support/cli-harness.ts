import { createServer } from 'node:http'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { runCli } from '../../src/cli.js'

export interface CliResult {
  exitCode: number
  stdout: string
  stderr: string
}

export interface MockRequest {
  method: string
  path: string
  query: URLSearchParams
  body: unknown
}

export interface MockReply {
  status?: number
  body?: unknown
  headers?: Record<string, string | string[]>
}

export type MockRoutes = Record<string, (request: MockRequest) => MockReply>

export interface MockApi {
  url: string
  requests: MockRequest[]
  close: () => Promise<void>
}

const ISOLATED_ENV_KEYS = [
  'MOLABEL_BASE_URL',
  'MOLABEL_SESSION',
  'MOLABEL_WORKSPACE',
] as const

export async function runCliCapture(args: string[]): Promise<CliResult> {
  const configDir = await mkdtemp(join(tmpdir(), 'molabel-cli-config-'))
  const savedEnv = ISOLATED_ENV_KEYS.map((key) => [key, process.env[key]])
  for (const key of ISOLATED_ENV_KEYS) {
    Reflect.deleteProperty(process.env, key)
  }
  const stdout: string[] = []
  const stderr: string[] = []
  const originalStdout = process.stdout.write.bind(process.stdout)
  const originalStderr = process.stderr.write.bind(process.stderr)
  process.stdout.write = captureInto(stdout)
  process.stderr.write = captureInto(stderr)
  try {
    const { exitCode } = await runCli([
      'node',
      'molabel',
      '--config',
      join(configDir, 'cli.json'),
      ...args,
    ])
    return { exitCode, stdout: stdout.join(''), stderr: stderr.join('') }
  } finally {
    process.stdout.write = originalStdout
    process.stderr.write = originalStderr
    for (const [key, value] of savedEnv) {
      if (key && value !== undefined) {
        process.env[key] = value
      }
    }
    await rm(configDir, { recursive: true, force: true })
  }
}

export function parseStdoutJson(result: CliResult): unknown {
  return JSON.parse(result.stdout) as unknown
}

export function readErrorCode(result: CliResult): string | undefined {
  const parsed = parseStdoutJson(result) as { error?: { code?: unknown } }
  return typeof parsed.error?.code === 'string' ? parsed.error.code : undefined
}

export async function startMockApi(routes: MockRoutes): Promise<MockApi> {
  const requests: MockRequest[] = []
  const server = createServer((req, res) => {
    void (async () => {
      const url = new URL(req.url ?? '/', 'http://127.0.0.1')
      const chunks: Buffer[] = []
      for await (const chunk of req as AsyncIterable<Buffer | string>) {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
      }
      const rawBody = Buffer.concat(chunks).toString('utf8')
      const request: MockRequest = {
        method: req.method ?? 'GET',
        path: url.pathname,
        query: url.searchParams,
        body: rawBody ? (JSON.parse(rawBody) as unknown) : null,
      }
      requests.push(request)
      const handler = routes[`${request.method} ${request.path}`]
      const reply = handler
        ? handler(request)
        : { status: 404, body: { detail: 'Not Found' } }
      res.statusCode = reply.status ?? 200
      res.setHeader('content-type', 'application/json')
      for (const [name, value] of Object.entries(reply.headers ?? {})) {
        res.setHeader(name, value)
      }
      res.end(JSON.stringify(reply.body ?? {}))
    })()
  })
  await new Promise<void>((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      resolve()
    })
  })
  const address = server.address()
  if (!address || typeof address === 'string') {
    throw new Error('mock API did not bind a TCP port')
  }
  return {
    url: `http://127.0.0.1:${String(address.port)}`,
    requests,
    close: () =>
      new Promise<void>((resolve, reject) => {
        server.close((error) => {
          if (error) {
            reject(error)
            return
          }
          resolve()
        })
      }),
  }
}

function captureInto(sink: string[]): typeof process.stdout.write {
  return (chunk: string | Uint8Array) => {
    sink.push(
      typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8'),
    )
    return true
  }
}
