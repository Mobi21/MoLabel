import {
  QueryClient,
  QueryClientProvider,
  type QueryKey,
} from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { agreementQuery, meQuery } from '@/api/queries'
import { Reply, fakeApi, type Call } from '@/test/fake-api'
import { AdjudicationPage } from './adjudication-page'

const SCHEMA = {
  task_schema_id: 's1',
  task_schema_slug: 'triage',
  version: 1,
  task_type: 'classification',
  title: 'Ticket triage',
  label_fields: [
    {
      name: 'intent',
      field_type: 'categorical',
      required: true,
      options: ['refund', 'bug', 'shipping', 'other'],
    },
  ],
  blind_review_policy: 'show_agent_outputs',
  workspace_id: 'w1',
  created_at: '2026-11-16T00:00:00Z',
  updated_at: '2026-11-16T00:00:00Z',
}

const SUMMARY = {
  record_id: 'rec1',
  record_external_id: 'ticket-1',
  task_schema_id: 's1',
  dataset_id: 'd1',
  severity: 'low',
  adjudication_type: 'subjective',
  fields_in_conflict: ['intent'],
  reviewer_count: 2,
  status: 'pending',
  adjudication_id: null,
}

function review(eventId: string, name: string, intent: string) {
  return {
    reviewer_id: name,
    reviewer_name: name,
    review_event_id: eventId,
    decision: 'edit',
    labels: { intent },
    created_at: '2026-11-16T00:00:00Z',
  }
}

function detail(reviews: ReturnType<typeof review>[]) {
  return {
    ...SUMMARY,
    record_text: 'Please refund my order.',
    reviewer_labels: reviews,
    agent_labels: [],
    disagreeing_fields: [],
    resolution: null,
  }
}

const READ = detail([review('e1', 'Ada', 'refund'), review('e2', 'Bo', 'bug')])
const CHANGED = detail([
  review('e1', 'Ada', 'refund'),
  review('e3', 'Bo', 'shipping'),
])

/** Serve the disagreement as READ, then as CHANGED once a reviewer corrects. */
function serve({ conflictOnce }: { conflictOnce: boolean }) {
  let current = READ
  let conflicts = conflictOnce ? 1 : 0
  return fakeApi([
    ['GET', /^\/api\/v1\/queues$/, () => ({ items: [] })],
    ['GET', /\/task-schemas\/s1$/, () => SCHEMA],
    [
      'GET',
      /\/disagreements$/,
      () => ({ queue_id: 'q1', items: [SUMMARY], total: 1, unresolved: 1 }),
    ],
    ['GET', /\/disagreements\/rec1$/, () => current],
    [
      'POST',
      /\/resolve$/,
      () => {
        if (conflicts > 0) {
          conflicts -= 1
          current = CHANGED
          return new Reply(409, {
            error: {
              code: 'CONFLICT',
              message: 'This disagreement changed since it was read; reload it',
            },
          })
        }
        return { ...current, status: 'resolved' }
      },
    ],
  ])
}

function renderAdjudication() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
  })
  queryClient.setQueryData(meQuery().queryKey, {
    reviewer_id: 'r1',
    display_name: 'Ada',
    avatar_color: null,
    is_operator: false,
    is_active: true,
    created_at: '2026-11-16T00:00:00Z',
    last_active_at: null,
    preferences: null,
    workspace_id: 'w1',
  })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/queues/q1/adjudication']}>
        <Routes>
          <Route
            path="/queues/:queueId/adjudication"
            element={<AdjudicationPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return queryClient
}

function press(key: string, init: KeyboardEventInit = {}) {
  fireEvent.keyDown(document.activeElement ?? document.body, { key, ...init })
}

function resolves(calls: Call[]) {
  return calls.filter((c) => c.path.endsWith('/resolve'))
}

describe('AdjudicationPage', () => {
  it('resolves naming the review events it showed', async () => {
    const calls = serve({ conflictOnce: false })
    renderAdjudication()
    await screen.findByRole('heading', { name: 'ticket-1' })

    press('b')
    press('Enter', { ctrlKey: true })

    await waitFor(() => {
      expect(resolves(calls)).toHaveLength(1)
    })
    expect(resolves(calls)[0]?.body).toMatchObject({
      resolved_labels: { intent: 'bug' },
      review_event_ids: ['e1', 'e2'],
    })
  })

  it('reloads a disagreement that changed, and drops the picks made on it', async () => {
    const calls = serve({ conflictOnce: true })
    renderAdjudication()
    await screen.findByRole('heading', { name: 'ticket-1' })

    press('b')
    press('Enter', { ctrlKey: true })

    expect(await screen.findByText(/changed since you opened it/)).toBeVisible()
    expect(await screen.findByRole('cell', { name: 'shipping' })).toBeVisible()
    expect(
      screen.getByRole('button', { name: 'bug', pressed: false }),
    ).toBeVisible()

    press('b')
    press('Enter', { ctrlKey: true })
    await waitFor(() => {
      expect(resolves(calls)).toHaveLength(2)
    })
    expect(resolves(calls)[1]?.body).toMatchObject({
      resolved_labels: { intent: 'shipping' },
      review_event_ids: ['e1', 'e3'],
    })
  })

  it('marks the queue agreement stale after a resolve', async () => {
    const calls = serve({ conflictOnce: false })
    const queryClient = renderAdjudication()
    const agreement: QueryKey = agreementQuery('w1', 'q1').queryKey
    queryClient.setQueryData(agreement, {})
    await screen.findByRole('heading', { name: 'ticket-1' })

    press('b')
    press('Enter', { ctrlKey: true })

    await waitFor(() => {
      expect(resolves(calls)).toHaveLength(1)
    })
    await waitFor(() => {
      expect(queryClient.getQueryState(agreement)?.isInvalidated).toBe(true)
    })
  })

  it('shows a failed task schema read with a retry, and recovers', async () => {
    let broken = true
    fakeApi([
      ['GET', /^\/api\/v1\/queues$/, () => ({ items: [] })],
      [
        'GET',
        /\/task-schemas\/s1$/,
        () =>
          broken
            ? new Reply(500, { error: { message: 'database is locked' } })
            : SCHEMA,
      ],
      [
        'GET',
        /\/disagreements$/,
        () => ({ queue_id: 'q1', items: [SUMMARY], total: 1, unresolved: 1 }),
      ],
      ['GET', /\/disagreements\/rec1$/, () => READ],
    ])
    renderAdjudication()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'database is locked',
    )
    broken = false
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(
      await screen.findByRole('heading', { name: 'ticket-1' }),
    ).toBeVisible()
  })
})
