import { client } from '@/api/generated/client.gen'
import { getMeQueryKey } from '@/api/generated/@tanstack/react-query.gen'
import { queryClient } from '@/lib/query-client'

/**
 * A 401 from any call but /me means the session ended mid-use, so the
 * session query refetches and the guard sends the reviewer to sign in.
 */
client.interceptors.response.use((response, request) => {
  if (response.status === 401 && !request.url.endsWith('/api/v1/me')) {
    void queryClient.invalidateQueries({ queryKey: getMeQueryKey() })
  }
  return response
})

/** The message of an API error body, `{ error: { message } }`, or a fallback. */
export function errorMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'error' in error) {
    const body = (error as { error?: { message?: unknown } }).error
    if (typeof body?.message === 'string') return body.message
  }
  if (error instanceof Error) return error.message
  return 'The request failed.'
}
