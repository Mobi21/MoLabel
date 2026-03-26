export function extractSessionTokenFromSetCookie(
  setCookieHeader: string[] | string | undefined,
): string | undefined {
  const values = Array.isArray(setCookieHeader)
    ? setCookieHeader
    : setCookieHeader
      ? [setCookieHeader]
      : []

  for (const value of values) {
    const match = /molabel_session=([^;]+)/.exec(value)
    if (match?.[1]) {
      return match[1]
    }
  }

  return undefined
}

export function readSetCookieHeaders(headers: Headers): string[] | undefined {
  const typedHeaders = headers as Headers & {
    getSetCookie?: () => string[]
  }

  if (typeof typedHeaders.getSetCookie === 'function') {
    return typedHeaders.getSetCookie()
  }

  const header = headers.get('set-cookie')
  return header ? [header] : undefined
}
