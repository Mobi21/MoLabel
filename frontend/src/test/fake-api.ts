import { client } from '@/api/generated/client.gen'

export interface Call {
  method: string
  path: string
  body: unknown
}

/** A canned reply with a status other than 200. */
export class Reply {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {}
}

type Route = [method: string, path: RegExp, reply: (call: Call) => unknown]

/**
 * Point the generated client at canned replies for one test, and record
 * every request it sends. A reply may be a promise, to hold a response back.
 * An unrouted request fails the test loudly.
 */
export function fakeApi(routes: Route[]) {
  const calls: Call[] = []
  client.setConfig({
    baseUrl: 'http://api.test',
    fetch: async (input: RequestInfo | URL) => {
      const request = input as Request
      const url = new URL(request.url)
      const text = await request.text()
      const call: Call = {
        method: request.method,
        path: url.pathname + url.search,
        body: text ? (JSON.parse(text) as unknown) : null,
      }
      calls.push(call)
      const route = routes.find(
        ([method, path]) => method === call.method && path.test(url.pathname),
      )
      if (!route) {
        throw new Error(`no fake route for ${call.method} ${call.path}`)
      }
      const result = await route[2](call)
      const reply = result instanceof Reply ? result : new Reply(200, result)
      return new Response(JSON.stringify(reply.body), {
        status: reply.status,
        headers: { 'content-type': 'application/json' },
      })
    },
  })
  return calls
}
