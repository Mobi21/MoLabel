export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly bodyText: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export interface ApiClientOptions {
  baseUrl: string
  sessionToken?: string
}

export class ApiClient {
  private readonly baseUrl: string

  private readonly sessionToken: string | undefined

  public constructor(options: ApiClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '')
    this.sessionToken = options.sessionToken ?? undefined
  }

  public async getJson<T>(path: string): Promise<T> {
    const response = await this.request(path, { method: 'GET' })
    return (await response.json()) as T
  }

  public async postJson<T>(path: string, body: unknown): Promise<T> {
    const response = await this.request(path, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    })
    return (await response.json()) as T
  }

  public async putJson<T>(path: string, body: unknown): Promise<T> {
    const response = await this.request(path, {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    })
    return (await response.json()) as T
  }

  public async postText(path: string, body: unknown): Promise<string> {
    const response = await this.request(path, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    })
    return response.text()
  }

  public async request(path: string, init: RequestInit): Promise<Response> {
    const url = new URL(path, `${this.baseUrl}/`).toString()
    const headers = new Headers(init.headers)
    if (this.sessionToken) {
      headers.set('Cookie', `molabel_session=${this.sessionToken}`)
    }

    const response = await fetch(url, {
      ...init,
      headers,
    })

    if (!response.ok) {
      const bodyText = await response.text()
      throw new ApiError(
        `Request failed with status ${String(response.status)}`,
        response.status,
        bodyText,
      )
    }

    return response
  }
}
