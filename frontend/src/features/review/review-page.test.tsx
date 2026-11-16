import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
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

interface Fixture {
  schema: typeof SCHEMA
  proposal: Record<string, unknown>
}

const TRIAGE: Fixture = { schema: SCHEMA, proposal: PROPOSAL }

const ENTITIES = [
  { text: 'order 42', type: 'ORDER', span: [12, 20] },
  { text: 'Ada', type: 'PERSON', span: [0, 3] },
]

const EXTRACTION: Fixture = {
  schema: {
    ...SCHEMA,
    label_fields: [
      {
        name: 'intent',
        field_type: 'categorical',
        required: true,
        options: ['refund', 'bug', 'shipping', 'other'],
      },
      { name: 'entities', field_type: 'json', required: true },
    ],
  },
  proposal: { intent: 'refund', entities: ENTITIES },
}

function task(policy: string, withProposal: boolean, fixture = TRIAGE) {
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
          labels: fixture.proposal,
          workspace_id: 'w1',
        }
      : null,
  }
}

function serve(policy: string, fixture = TRIAGE) {
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
      () => ({ task: task(policy, !blind, fixture), queue_empty: false }),
    ],
    ['GET', /\/task-schemas\/s1$/, () => fixture.schema],
    [
      'POST',
      /\/reveal-ai$/,
      () => ({ task: { ...task(policy, true, fixture), ai_revealed: true } }),
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
    [
      'GET',
      /\/review-tasks\/t1$/,
      () => ({ ...task(policy, !blind, fixture) }),
    ],
  ])
}

interface StoredReview {
  review_event_id: string
  decision: string | null
  labels: Record<string, unknown>
  rationale: string | null
  ai_was_revealed: boolean
  created_at: string
}

/**
 * A reviewer who submitted ticket-0 and holds ticket-1. The server stores
 * each correction of ticket-0 as its new counted review, and holds back
 * every later read of ticket-0 until the test calls ``release``.
 */
function serveTrail(
  first: Omit<StoredReview, 'created_at' | 'ai_was_revealed'>,
) {
  let review: StoredReview = {
    ...first,
    ai_was_revealed: false,
    created_at: '2026-11-16T00:00:00Z',
  }
  let held: Promise<void> | null = null
  let release = () => {}
  const submittedTask = () => ({
    ...task('show_agent_outputs', true),
    id: 't0',
    record_id: 'rec0',
    record_external_id: 'ticket-0',
    status: 'submitted',
    review,
  })
  const calls = fakeApi([
    ['GET', /^\/api\/v1\/queues$/, () => ({ items: [] })],
    [
      'GET',
      /\/my-tasks$/,
      () => ({
        queue_id: 'q1',
        items: [
          {
            task_id: 't0',
            record_id: 'rec0',
            record_external_id: 'ticket-0',
            status: 'submitted',
            decision: review.decision,
          },
          {
            task_id: 't1',
            record_id: 'rec1',
            record_external_id: 'ticket-1',
            status: 'claimed',
          },
        ],
      }),
    ],
    ['GET', /\/task-schemas\/s1$/, () => SCHEMA],
    ['GET', /\/review-tasks\/t1$/, () => task('show_agent_outputs', true)],
    [
      'GET',
      /\/review-tasks\/t0$/,
      async () => {
        await held
        return submittedTask()
      },
    ],
    [
      'POST',
      /\/review-tasks\/t0\/correct$/,
      (call) => {
        const body = call.body as Pick<
          StoredReview,
          'decision' | 'labels' | 'rationale'
        >
        review = {
          ...review,
          ...body,
          review_event_id: `${review.review_event_id}+`,
        }
        held = new Promise((done) => {
          release = done
        })
        return {
          event: {
            ...review,
            id: review.review_event_id,
            review_task_id: 't0',
            record_id: 'rec0',
            task_schema_id: 's1',
            task_schema_version: 1,
            reviewer_id: 'r1',
            source: 'human',
            supersedes_event_id: first.review_event_id,
            workspace_id: 'w1',
          },
        }
      },
    ],
  ])
  return {
    calls,
    release: () => {
      release()
    },
    /** Another session corrects ticket-0. */
    correctElsewhere: (labels: Record<string, unknown>) => {
      review = { ...review, labels, review_event_id: 'elsewhere' }
    },
  }
}

function corrections(calls: Call[]) {
  return calls.filter((c) => c.path.endsWith('/correct'))
}

function intentButton(name: string) {
  return within(screen.getByRole('group', { name: 'intent' })).getByRole(
    'button',
    { name },
  )
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
  return queryClient
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

  it('keeps a JSON field structured through an edit of another field', async () => {
    const calls = serve('show_agent_outputs', EXTRACTION)
    renderReview()
    await screen.findByRole('heading', { name: 'ticket-1' })
    const entities = screen.getByRole('textbox', { name: 'entities' })
    expect(JSON.parse((entities as HTMLTextAreaElement).value)).toEqual(
      ENTITIES,
    )

    press('2')
    press('Enter', { ctrlKey: true })

    expect(await submitted(calls)).toMatchObject({
      decision: 'edit',
      labels: { intent: 'bug', entities: ENTITIES },
    })
  })

  it('will not submit JSON that does not parse, and sends it parsed once it does', async () => {
    const calls = serve('show_agent_outputs', EXTRACTION)
    renderReview()
    await screen.findByRole('heading', { name: 'ticket-1' })
    const entities = screen.getByRole('textbox', { name: 'entities' })

    fireEvent.change(entities, { target: { value: '[{"text": "Ada"' } })
    press('Enter', { ctrlKey: true })
    expect(await screen.findByRole('alert')).toHaveTextContent('entities')
    expect(calls.some((c) => c.path.endsWith('/submit'))).toBe(false)

    fireEvent.change(entities, {
      target: { value: '[{"text": "Ada", "type": "PERSON"}]' },
    })
    press('Enter', { ctrlKey: true })
    expect(await submitted(calls)).toMatchObject({
      decision: 'edit',
      labels: {
        intent: 'refund',
        entities: [{ text: 'Ada', type: 'PERSON' }],
      },
    })
  })

  it('shows a correction on return, and never sends the labels it replaced', async () => {
    const { calls, release } = serveTrail({
      review_event_id: 'e0',
      decision: 'edit',
      labels: { intent: 'bug', urgent: false },
      rationale: null,
    })
    renderReview()
    await screen.findByRole('heading', { name: 'ticket-1' })

    press('k')
    await screen.findByRole('heading', { name: 'ticket-0' })
    expect(intentButton('bug')).toHaveAttribute('aria-pressed', 'true')
    press('3')
    press('Enter', { ctrlKey: true })
    await screen.findByRole('heading', { name: 'ticket-1' })
    expect(corrections(calls)[0]?.body).toMatchObject({
      labels: { intent: 'shipping' },
    })

    press('k')
    await screen.findByRole('heading', { name: 'ticket-0' })
    expect(intentButton('shipping')).toHaveAttribute('aria-pressed', 'true')
    press('Enter', { ctrlKey: true })
    await screen.findByRole('heading', { name: 'ticket-1' })
    expect(corrections(calls)).toHaveLength(1)
    release()
  })

  it('saves a correction that changes only the note, keeping the decision', async () => {
    const { calls } = serveTrail({
      review_event_id: 'e0',
      decision: 'reject',
      labels: { intent: 'bug', urgent: false },
      rationale: null,
    })
    renderReview()
    await screen.findByRole('heading', { name: 'ticket-1' })
    press('k')
    await screen.findByRole('heading', { name: 'ticket-0' })

    fireEvent.change(screen.getByRole('textbox', { name: /Note/ }), {
      target: { value: 'Not a bug report; the order never shipped.' },
    })
    press('Enter', { ctrlKey: true })

    await waitFor(() => {
      expect(corrections(calls)).toHaveLength(1)
    })
    expect(corrections(calls)[0]?.body).toEqual({
      decision: 'reject',
      labels: { intent: 'bug', urgent: false },
      rationale: 'Not a bug report; the order never shipped.',
    })
  })

  it('starts the form over when the review on the server changes under it', async () => {
    const { correctElsewhere } = serveTrail({
      review_event_id: 'e0',
      decision: 'edit',
      labels: { intent: 'bug', urgent: false },
      rationale: null,
    })
    const queryClient = renderReview()
    await screen.findByRole('heading', { name: 'ticket-1' })
    press('k')
    await screen.findByRole('heading', { name: 'ticket-0' })

    correctElsewhere({ intent: 'other', urgent: false })
    await queryClient.invalidateQueries()

    await waitFor(() => {
      expect(intentButton('other')).toHaveAttribute('aria-pressed', 'true')
    })
  })
})
