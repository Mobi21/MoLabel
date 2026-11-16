import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { meQuery } from '@/api/queries'
import { fakeApi, type Call } from '@/test/fake-api'
import { ReviewPage } from './review-page'

const PROPOSAL = { intent: 'refund', urgent: false, note: '' }

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
    { name: 'urgent', field_type: 'bool', required: true },
    { name: 'note', field_type: 'text', required: false },
  ],
  blind_review_policy: 'show_agent_outputs',
  workspace_id: 'w1',
  created_at: '2026-11-16T00:00:00Z',
  updated_at: '2026-11-16T00:00:00Z',
}

function task(policy: string, withProposal: boolean) {
  return {
    id: 't1',
    queue_id: 'q1',
    record_id: 'rec1',
    task_schema_id: 's1',
    status: 'claimed',
    priority: 1,
    created_at: '2026-11-16T00:00:00Z',
    updated_at: '2026-11-16T00:00:00Z',
    workspace_id: 'w1',
    dataset_id: 'd1',
    record_external_id: 'ticket-1',
    record_text: 'Please refund my order, it arrived broken.',
    blind_review_policy: policy,
    ai_revealed: false,
    agent_output: withProposal
      ? {
          id: 'o1',
          agent_run_id: 'run1',
          record_id: 'rec1',
          task_schema_id: 's1',
          output_type: 'labels',
          labels: PROPOSAL,
          workspace_id: 'w1',
        }
      : null,
  }
}

function serve(policy: string) {
  const blind = policy === 'hide_agent_outputs_by_default'
  return fakeApi([
    [
      'GET',
      /^\/api\/v1\/queues$/,
      () => ({
        items: [
          {
            queue_id: 'q1',
            workspace_id: 'w1',
            task_schema_id: 's1',
            task_schema_title: 'Ticket triage',
            kind: 'review',
            blind_review_policy: policy,
            total: 1,
            available: 0,
            claimed: 1,
            submitted: 0,
            skipped: 0,
            my_remaining: 1,
            my_submitted: 0,
            created_at: '2026-11-16T00:00:00Z',
          },
        ],
      }),
    ],
    ['GET', /\/my-tasks$/, () => ({ queue_id: 'q1', items: [] })],
    [
      'POST',
      /\/queues\/q1\/claim$/,
      () => ({ task: task(policy, !blind), queue_empty: false }),
    ],
    ['GET', /\/task-schemas\/s1$/, () => SCHEMA],
    [
      'POST',
      /\/reveal-ai$/,
      () => ({ task: { ...task(policy, true), ai_revealed: true } }),
    ],
    [
      'POST',
      /\/submit$/,
      () => ({
        submitted_task: { ...task(policy, false), status: 'submitted' },
        next_task: null,
        queue_empty: true,
      }),
    ],
    ['GET', /\/review-tasks\/t1$/, () => ({ ...task(policy, !blind) })],
  ])
}

function renderReview() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
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
      <MemoryRouter initialEntries={['/queues/q1/review']}>
        <Routes>
          <Route path="/queues/:queueId/review" element={<ReviewPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function press(key: string, init: KeyboardEventInit = {}) {
  fireEvent.keyDown(document.activeElement ?? document.body, { key, ...init })
}

async function submitted(calls: Call[]) {
  await waitFor(() => {
    expect(calls.some((c) => c.path.endsWith('/submit'))).toBe(true)
  })
  return calls.find((c) => c.path.endsWith('/submit'))?.body
}

describe('ReviewPage', () => {
  it('focuses the item, and submits an accept with the proposal kept', async () => {
    const calls = serve('show_agent_outputs')
    renderReview()
    const heading = await screen.findByRole('heading', { name: 'ticket-1' })
    expect(heading).toHaveFocus()
    expect(screen.getByTestId('ai-proposal')).toHaveTextContent('refund')

    press('Enter', { ctrlKey: true })

    expect(await submitted(calls)).toMatchObject({
      decision: 'accept',
      labels: PROPOSAL,
      auto_claim_next: true,
    })
  })

  it('submits an edit with the labels the reviewer changed by key', async () => {
    const calls = serve('show_agent_outputs')
    renderReview()
    await screen.findByRole('heading', { name: 'ticket-1' })

    press('4')
    expect(screen.getByTestId('decision-preview')).toHaveTextContent(
      'edit · intent',
    )
    press('Enter', { ctrlKey: true })

    expect(await submitted(calls)).toMatchObject({
      decision: 'edit',
      labels: { ...PROPOSAL, intent: 'other' },
    })
  })

  it('keeps a blind proposal out of the page until R reveals it', async () => {
    const calls = serve('hide_agent_outputs_by_default')
    renderReview()
    await screen.findByRole('heading', { name: 'ticket-1' })
    expect(screen.queryByTestId('ai-proposal')).toBeNull()

    press('r')

    expect(await screen.findByTestId('ai-proposal')).toHaveTextContent('refund')
    expect(calls.filter((c) => c.path.endsWith('/reveal-ai'))).toHaveLength(1)
    press('Enter', { ctrlKey: true })
    expect(await submitted(calls)).toMatchObject({ decision: 'accept' })
  })

  it('will not submit a blind item until required fields have values', async () => {
    const calls = serve('hide_agent_outputs_by_default')
    renderReview()
    await screen.findByRole('heading', { name: 'ticket-1' })

    press('Enter', { ctrlKey: true })
    expect(await screen.findByRole('alert')).toHaveTextContent('intent, urgent')
    expect(calls.some((c) => c.path.endsWith('/submit'))).toBe(false)

    press('2')
    press('1')
    press('Enter', { ctrlKey: true })
    expect(await submitted(calls)).toMatchObject({
      decision: null,
      labels: { intent: 'bug', urgent: true },
    })
  })
})
