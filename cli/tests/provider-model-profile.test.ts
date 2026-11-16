import { createServer } from 'node:http'

import { afterEach, describe, expect, it } from 'vitest'

import { runCli } from '../src/cli.js'

interface RecordedRequest {
  body: unknown
  method: string
  path: string
}

interface MockApiServer {
  close: () => Promise<void>
  requests: RecordedRequest[]
  url: string
}

const openServers: MockApiServer[] = []

afterEach(async () => {
  await Promise.all(openServers.splice(0).map((server) => server.close()))
})

async function captureCliJson(
  argv: string[],
): Promise<{ exitCode: number; json: unknown }> {
  const chunks: string[] = []
  const originalWrite = process.stdout.write.bind(process.stdout)
  process.stdout.write = ((chunk: string | Uint8Array) => {
    chunks.push(
      typeof chunk === 'string' ? chunk : Buffer.from(chunk).toString('utf8'),
    )
    return true
  })

  try {
    const result = await runCli(argv)
    const stdout = chunks.join('').trim()
    return {
      exitCode: result.exitCode,
      json: stdout ? (JSON.parse(stdout) as unknown) : null,
    }
  } finally {
    process.stdout.write = originalWrite
  }
}

async function createMockApiServer(): Promise<MockApiServer> {
  const requests: RecordedRequest[] = []
  const state = {
    createdProfileId: '00000000-0000-0000-0000-00000000c0de',
  }

  const server = createServer((req, res) => {
    void (async () => {
      const url = new URL(req.url ?? '/', 'http://127.0.0.1')
      const chunks: Buffer[] = []
      for await (const chunk of req as AsyncIterable<Buffer | string>) {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
      }
      const rawBody = Buffer.concat(chunks).toString('utf8')
      const body = rawBody ? (JSON.parse(rawBody) as unknown) : null
      requests.push({
        body,
        method: req.method ?? 'GET',
        path: `${url.pathname}${url.search}`,
      })

      const sendJson = (status: number, payload: unknown) => {
        res.statusCode = status
        res.setHeader('content-type', 'application/json')
        res.end(JSON.stringify(payload))
      }

      if (req.method === 'GET' && url.pathname === '/api/v1/providers') {
        sendJson(200, {
          providers: [
            {
              provider_type: 'anthropic',
              display_name: 'MiniMax Anthropic Adapter',
            },
          ],
        })
        return
      }

      if (req.method === 'POST' && url.pathname === '/api/v1/providers/scan') {
        sendJson(200, {
          providers: [
            {
              provider_type: 'anthropic',
              display_name: 'MiniMax Anthropic Adapter',
            },
          ],
        })
        return
      }

      if (
        req.method === 'GET' &&
        url.pathname === '/api/v1/providers/health/anthropic'
      ) {
        sendJson(200, {
          provider_type: 'anthropic',
          health: { status: 'healthy', message: 'ok' },
        })
        return
      }

      if (
        req.method === 'GET' &&
        url.pathname === '/api/v1/providers/models/anthropic'
      ) {
        sendJson(200, {
          provider_type: 'anthropic',
          models: [
            {
              identifier: 'MiniMax-M2.7-highspeed',
              display_name: 'MiniMax 2.7 highspeed',
            },
          ],
        })
        return
      }

      if (
        req.method === 'GET' &&
        url.pathname === '/api/v1/providers/hf/auth'
      ) {
        sendJson(200, {
          is_authenticated: false,
          has_write_access: false,
        })
        return
      }

      if (req.method === 'GET' && url.pathname === '/api/v1/model-profiles') {
        sendJson(200, [
          {
            id: state.createdProfileId,
            model_profile_slug: 'minimax-grounded',
            provider_type: 'anthropic',
            provider_name: 'MiniMax',
            model_identifier: 'MiniMax-M2.7-highspeed',
            transport: 'https',
          },
        ])
        return
      }

      if (req.method === 'POST' && url.pathname === '/api/v1/model-profiles') {
        const payload = body as Record<string, unknown>
        sendJson(201, {
          id: state.createdProfileId,
          model_profile_slug: payload.model_profile_slug,
          provider_type: payload.provider_type,
          provider_name: payload.provider_name,
          model_identifier: payload.model_identifier,
          transport: payload.transport ?? 'https',
        })
        return
      }

      if (
        req.method === 'GET' &&
        url.pathname === `/api/v1/model-profiles/${state.createdProfileId}`
      ) {
        sendJson(200, {
          id: state.createdProfileId,
          model_profile_slug: 'minimax-grounded',
          provider_type: 'anthropic',
          provider_name: 'MiniMax',
          model_identifier: 'MiniMax-M2.7-highspeed',
          transport: 'https',
        })
        return
      }

      if (
        req.method === 'PATCH' &&
        url.pathname === `/api/v1/model-profiles/${state.createdProfileId}`
      ) {
        const payload = body as Record<string, unknown>
        sendJson(200, {
          id: state.createdProfileId,
          model_profile_slug: payload.model_profile_slug ?? 'minimax-grounded',
          provider_type: 'anthropic',
          provider_name: payload.provider_name ?? 'MiniMax',
          model_identifier:
            payload.model_identifier ?? 'MiniMax-M2.7-highspeed',
          transport: payload.transport ?? 'https',
        })
        return
      }

      if (
        req.method === 'POST' &&
        url.pathname === `/api/v1/model-profiles/${state.createdProfileId}/test`
      ) {
        sendJson(200, {
          profile_id: state.createdProfileId,
          health: { status: 'healthy', message: 'ok' },
          available_models: [{ identifier: 'MiniMax-M2.7-highspeed' }],
          error: null,
        })
        return
      }

      if (
        req.method === 'DELETE' &&
        url.pathname === `/api/v1/model-profiles/${state.createdProfileId}`
      ) {
        res.statusCode = 204
        res.end()
        return
      }

      res.statusCode = 404
      res.end(JSON.stringify({ error: 'not found' }))
    })().catch((error: unknown) => {
      res.statusCode = 500
      res.end(error instanceof Error ? error.message : 'Mock server error')
    })
  })

  await new Promise<void>((resolvePromise) => {
    server.listen(0, '127.0.0.1', () => {
      resolvePromise()
    })
  })

  const address = server.address()
  if (!address || typeof address === 'string') {
    throw new Error('Failed to bind mock API server')
  }

  const handle: MockApiServer = {
    close: () =>
      new Promise<void>((resolvePromise, reject) => {
        server.close((error) => {
          if (error) {
            reject(error)
            return
          }
          resolvePromise()
        })
      }),
    requests,
    url: `http://127.0.0.1:${String(address.port)}`,
  }
  openServers.push(handle)
  return handle
}

describe('provider and model-profile commands', () => {
  it('exercises provider discovery commands', async () => {
    const server = await createMockApiServer()

    const listResult = await captureCliJson([
      'node',
      'molabel',
      '--base-url',
      server.url,
      '--json',
      'provider',
      'list',
    ])
    expect(listResult.exitCode).toBe(0)
    expect(listResult.json).toEqual({
      providers: [
        {
          provider_type: 'anthropic',
          display_name: 'MiniMax Anthropic Adapter',
        },
      ],
    })

    const healthResult = await captureCliJson([
      'node',
      'molabel',
      '--base-url',
      server.url,
      '--json',
      'provider',
      'health',
      'anthropic',
      '--provider-base-url',
      'https://api.minimax.io/anthropic',
      '--auth-ref',
      'ANTHROPIC_API_KEY',
    ])
    expect(healthResult.exitCode).toBe(0)
    expect(healthResult.json).toEqual({
      provider_type: 'anthropic',
      health: { status: 'healthy', message: 'ok' },
    })

    const modelsResult = await captureCliJson([
      'node',
      'molabel',
      '--base-url',
      server.url,
      '--json',
      'provider',
      'models',
      'anthropic',
    ])
    expect(modelsResult.exitCode).toBe(0)
    expect(modelsResult.json).toEqual({
      provider_type: 'anthropic',
      models: [
        {
          identifier: 'MiniMax-M2.7-highspeed',
          display_name: 'MiniMax 2.7 highspeed',
        },
      ],
    })

    const authResult = await captureCliJson([
      'node',
      'molabel',
      '--base-url',
      server.url,
      '--json',
      'provider',
      'hf-auth',
    ])
    expect(authResult.exitCode).toBe(0)
    expect(authResult.json).toEqual({
      is_authenticated: false,
      has_write_access: false,
    })

    const providerHealthPath = server.requests.find((request) =>
      request.path.startsWith('/api/v1/providers/health/anthropic?'),
    )?.path
    expect(providerHealthPath).toBeDefined()
    expect(providerHealthPath).toContain('auth_ref=ANTHROPIC_API_KEY')
    expect(providerHealthPath).toContain('base_url=')
  })

  it('exercises model-profile CRUD and connectivity commands', async () => {
    const server = await createMockApiServer()

    const createResult = await captureCliJson([
      'node',
      'molabel',
      '--base-url',
      server.url,
      '--json',
      'model-profile',
      'create',
      '--body-text',
      JSON.stringify({
        model_profile_slug: 'minimax-grounded',
        provider_type: 'anthropic',
        provider_name: 'MiniMax',
        model_identifier: 'MiniMax-M2.7-highspeed',
        auth_ref: 'ANTHROPIC_API_KEY',
        base_url: 'https://api.minimax.io/anthropic',
        supports_structured_output: true,
      }),
    ])
    expect(createResult.exitCode).toBe(0)
    expect(createResult.json).toEqual({
      id: '00000000-0000-0000-0000-00000000c0de',
      model_profile_slug: 'minimax-grounded',
      provider_type: 'anthropic',
      provider_name: 'MiniMax',
      model_identifier: 'MiniMax-M2.7-highspeed',
      transport: 'https',
    })

    const listResult = await captureCliJson([
      'node',
      'molabel',
      '--base-url',
      server.url,
      '--json',
      'model-profile',
      'list',
      '--provider-type',
      'anthropic',
    ])
    expect(listResult.exitCode).toBe(0)
    expect(listResult.json).toEqual([
      {
        id: '00000000-0000-0000-0000-00000000c0de',
        model_profile_slug: 'minimax-grounded',
        provider_type: 'anthropic',
        provider_name: 'MiniMax',
        model_identifier: 'MiniMax-M2.7-highspeed',
        transport: 'https',
      },
    ])

    const getResult = await captureCliJson([
      'node',
      'molabel',
      '--base-url',
      server.url,
      '--json',
      'model-profile',
      'get',
      '00000000-0000-0000-0000-00000000c0de',
    ])
    expect(getResult.exitCode).toBe(0)

    const updateResult = await captureCliJson([
      'node',
      'molabel',
      '--base-url',
      server.url,
      '--json',
      'model-profile',
      'update',
      '00000000-0000-0000-0000-00000000c0de',
      '--body-text',
      JSON.stringify({
        provider_name: 'MiniMax Updated',
      }),
    ])
    expect(updateResult.exitCode).toBe(0)
    expect(updateResult.json).toEqual({
      id: '00000000-0000-0000-0000-00000000c0de',
      model_profile_slug: 'minimax-grounded',
      provider_type: 'anthropic',
      provider_name: 'MiniMax Updated',
      model_identifier: 'MiniMax-M2.7-highspeed',
      transport: 'https',
    })

    const testResult = await captureCliJson([
      'node',
      'molabel',
      '--base-url',
      server.url,
      '--json',
      'model-profile',
      'test',
      '00000000-0000-0000-0000-00000000c0de',
    ])
    expect(testResult.exitCode).toBe(0)
    expect(testResult.json).toEqual({
      profile_id: '00000000-0000-0000-0000-00000000c0de',
      health: { status: 'healthy', message: 'ok' },
      available_models: [{ identifier: 'MiniMax-M2.7-highspeed' }],
      error: null,
    })

    const deleteResult = await captureCliJson([
      'node',
      'molabel',
      '--base-url',
      server.url,
      '--json',
      'model-profile',
      'delete',
      '00000000-0000-0000-0000-00000000c0de',
    ])
    expect(deleteResult.exitCode).toBe(0)
    expect(deleteResult.json).toEqual({
      ok: true,
      deleted: '00000000-0000-0000-0000-00000000c0de',
    })

    expect(server.requests.map((request) => request.path)).toContain(
      '/api/v1/model-profiles?provider_type=anthropic',
    )
  })
})
