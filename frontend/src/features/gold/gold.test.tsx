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
import { AdjudicationPage } from '@/features/adjudication/adjudication-page'
import { CalibrationPage } from '@/features/calibration/calibration-page'
import { fakeApi, type Call } from '@/test/fake-api'
import { GoldSetsPage } from './gold-sets-page'

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

function goldSet(id: string, name: string, schema: string, version = 1) {
  return {
    gold_set_id: id,
    name,
    task_schema: schema,
    version,
    item_count: version - 1,
    content_hash: 'sha256:abc',
    previous_hash: null,
    updated_at: '2026-11-17T00:00:00Z',
    path: `gold/${id}/gold.yaml`,
    content_hash_matches: true,
  }
}

const TRIAGE_GOLD = goldSet('triage-gold', 'Triage gold', 'triage')
const TOPICS_GOLD = goldSet('topics-gold', 'Topics gold', 'topics')

function item(externalId: string, intent: string) {
  return {
    item_id: `item-${externalId}`,
    input_ref: {
      dataset: 'tickets',
      external_id: externalId,
      record_id: 'rec1',
    },
    input: { text: 'Please refund my order.' },
    input_hash: 'sha256:in',
    expected: { intent },
    content_hash: `sha256:${intent}`,
    provenance: {
      source: 'adjudication',
      queue_id: 'q1',
      reviews: [],
      reviewer_ids: ['r1'],
      ai_revealed: true,
      accepted_ai_proposal: false,
      promoted_at: '2026-11-17T00:00:00Z',
      promoted_by: 'r1',
    },
  }
}

function report(overrides: Record<string, unknown> = {}) {
  return {
    gold_set: { ...TRIAGE_GOLD, version: 2, item_count: 1 },
    written: true,
    counts: { added: 1, duplicates: 0, conflicts: 0, skipped: 0 },
    added: [item('ticket-1', 'refund')],
    duplicates: [],
    conflicts: [],
    skipped: [],
    ...overrides,
  }
}

const RESOLVED = {
  record_id: 'rec1',
  record_external_id: 'ticket-1',
  task_schema_id: 's1',
  dataset_id: 'd1',
  severity: 'low',
  adjudication_type: 'subjective',
  fields_in_conflict: ['intent'],
  reviewer_count: 2,
  status: 'resolved',
  adjudication_id: 'a1',
  record_text: 'Please refund my order.',
  reviewer_labels: [
    {
      reviewer_id: 'Ada',
      reviewer_name: 'Ada',
      review_event_id: 'e1',
      decision: 'edit',
      labels: { intent: 'refund' },
      created_at: '2026-11-16T00:00:00Z',
    },
  ],
  agent_labels: [],
  disagreeing_fields: [],
  resolution: {
    adjudication_id: 'a1',
    resolution: 'resolve',
    resolved_labels: { intent: 'refund' },
    adjudicator_id: 'r1',
    adjudicator_name: 'Ada',
    resolved_at: '2026-11-17T00:00:00Z',
  },
}

function client() {
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
  return queryClient
}

function renderAt(path: string, route: string, element: React.ReactNode) {
  render(
    <QueryClientProvider client={client()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function press(key: string) {
  fireEvent.keyDown(document.activeElement ?? document.body, { key })
}

function promotions(calls: Call[]) {
  return calls.filter((c) => c.path.endsWith('/promote'))
}

function serveAdjudication(
  disagreement: unknown,
  sets: unknown[],
  promoted: () => unknown = () => report(),
) {
  return fakeApi([
    ['GET', /^\/api\/v1\/queues$/, () => ({ items: [] })],
    ['GET', /\/task-schemas\/s1$/, () => SCHEMA],
    [
      'GET',
      /\/disagreements$/,
      () => ({
        queue_id: 'q1',
        items: [disagreement],
        total: 1,
        unresolved: 0,
      }),
    ],
    ['GET', /\/disagreements\/rec1$/, () => disagreement],
    ['GET', /^\/api\/v1\/gold-sets$/, () => ({ items: sets })],
    ['POST', /^\/api\/v1\/gold-sets\/[^/]+\/promote$/, promoted],
  ])
}

function renderAdjudication() {
  renderAt(
    '/queues/q1/adjudication',
    '/queues/:queueId/adjudication',
    <AdjudicationPage />,
  )
}

describe('Promote to gold on the adjudication screen', () => {
  it('promotes the resolved record into a set of its task schema with G', async () => {
    const calls = serveAdjudication(RESOLVED, [TOPICS_GOLD, TRIAGE_GOLD])
    renderAdjudication()
    const panel = await screen.findByRole('region', {
      name: 'Promote to gold',
    })
    const picker = await within(panel).findByRole('combobox', {
      name: 'Gold set',
    })
    expect(
      within(picker)
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toEqual(['Triage gold · v1 · 0 items'])

    press('g')

    await waitFor(() => {
      expect(promotions(calls)).toHaveLength(1)
    })
    expect(promotions(calls)[0]).toMatchObject({
      path: '/api/v1/gold-sets/triage-gold/promote',
      body: { queue_id: 'q1', record_ids: ['rec1'] },
    })
    expect(
      await within(panel).findByTestId('promote-result'),
    ).toHaveTextContent(
      'Added 1 item to Triage gold, now version 2 with 1 item.',
    )
  })

  it('reports a conflict with gold and says gold is kept', async () => {
    serveAdjudication(RESOLVED, [TRIAGE_GOLD], () =>
      report({
        gold_set: TRIAGE_GOLD,
        written: false,
        counts: { added: 0, duplicates: 0, conflicts: 1, skipped: 0 },
        added: [],
        conflicts: [
          {
            item_id: 'item-ticket-1',
            fields: ['intent'],
            gold: item('ticket-1', 'bug'),
            other: item('ticket-1', 'refund'),
          },
        ],
      }),
    )
    renderAdjudication()
    await screen.findByRole('region', { name: 'Promote to gold' })
    fireEvent.click(
      await screen.findByRole('button', { name: /Promote this record/ }),
    )

    expect(await screen.findByTestId('promote-conflict')).toHaveTextContent(
      'ticket-1 conflicts with gold on intent: gold has bug, this has refund. Gold is kept',
    )
    expect(screen.getByTestId('promote-result')).toHaveTextContent(
      'Nothing added to Triage gold; it stays at version 1.',
    )
  })

  it('offers no promotion before the disagreement is resolved', async () => {
    const pending = { ...RESOLVED, status: 'pending', resolution: null }
    const calls = serveAdjudication(pending, [TRIAGE_GOLD])
    renderAdjudication()
    await screen.findByRole('heading', { name: 'ticket-1' })

    press('g')

    expect(
      screen.queryByRole('region', { name: 'Promote to gold' }),
    ).not.toBeInTheDocument()
    expect(promotions(calls)).toEqual([])
  })

  it('says how to create a set when none holds the task schema', async () => {
    const calls = serveAdjudication(RESOLVED, [TOPICS_GOLD])
    renderAdjudication()

    expect(
      await screen.findByText(/No gold set holds triage yet/),
    ).toHaveTextContent('molabel gold create <slug> --task-schema triage')
    press('g')
    expect(promotions(calls)).toEqual([])
  })
})

function serveCalibration(kind: string, calls?: { promoted?: () => unknown }) {
  const scope = {
    pooled: { krippendorff_alpha: 0.8, percent_agreement: 0.9, comparisons: 6 },
    fields: {},
    skipped_fields: {},
  }
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
            kind,
            total: 12,
            available: 0,
            claimed: 0,
            submitted: 12,
            skipped: 0,
            closed: 0,
            created_at: '2026-11-16T00:00:00Z',
          },
        ],
      }),
    ],
    ['GET', /\/task-schemas\/s1$/, () => SCHEMA],
    [
      'GET',
      /^\/api\/v1\/quality\/agreement$/,
      () => ({
        workspace_id: 'w1',
        queue_id: 'q1',
        record_count: 6,
        reviewer_count: 2,
        inter_annotator: scope,
        human_agent: scope,
        warnings: [],
      }),
    ],
    ['GET', /^\/api\/v1\/gold-sets$/, () => ({ items: [TRIAGE_GOLD] })],
    [
      'GET',
      /^\/api\/v1\/calibration\/queues\/q1$/,
      () => ({
        queue_id: 'q1',
        gold_set_id: 'triage-gold',
        gold_version: 3,
        queue_gold_version: 2,
        items: 6,
        fields: ['intent'],
        reviewers: [
          {
            reviewer_id: 'r2',
            reviewer_name: 'Bo',
            items_answered: 6,
            exact_match: 0.5,
            pooled: { accuracy: 0.5, cohen_kappa: 0, compared: 6, missing: 0 },
            fields: {
              intent: {
                accuracy: 0.5,
                cohen_kappa: 0,
                compared: 6,
                missing: 0,
              },
            },
          },
        ],
        warnings: ['Gold set triage-gold is at version 3.'],
      }),
    ],
    [
      'POST',
      /\/promote$/,
      calls?.promoted ??
        (() =>
          report({
            counts: { added: 5, duplicates: 0, conflicts: 0, skipped: 1 },
            skipped: [
              {
                record_id: 'rec3',
                external_id: 'ticket-3',
                reason: 'unresolved_disagreement',
                message:
                  'The reviewers disagree and no adjudication resolved it.',
              },
            ],
          })),
    ],
  ])
}

describe('Promote to gold on the calibration screen', () => {
  it('promotes every eligible record of a review queue and names the skipped', async () => {
    const calls = serveCalibration('review')
    renderAt(
      '/queues/q1/calibration',
      '/queues/:queueId/calibration',
      <CalibrationPage />,
    )
    await screen.findByRole('combobox', { name: 'Gold set' })

    press('g')

    await waitFor(() => {
      expect(promotions(calls)).toHaveLength(1)
    })
    expect(promotions(calls)[0]?.body).toEqual({
      queue_id: 'q1',
      record_ids: null,
    })
    expect(await screen.findByTestId('promote-result')).toHaveTextContent(
      'Skipped ticket-3: The reviewers disagree and no adjudication resolved it.',
    )
  })

  it('shows each reviewer against gold on a calibration queue', async () => {
    serveCalibration('calibrate')
    renderAt(
      '/queues/q1/calibration',
      '/queues/:queueId/calibration',
      <CalibrationPage />,
    )

    const row = await screen.findByTestId('reviewer-against-gold')
    expect(
      within(row)
        .getAllByRole('cell')
        .map((cell) => cell.textContent),
    ).toEqual(['6', '50.0%', '50.0%', '0.000', '50.0%', '0.000'])
    expect(within(row).getByRole('rowheader')).toHaveTextContent('Bo')
    expect(
      screen.getByText('Gold set triage-gold is at version 3.'),
    ).toBeVisible()
  })

  it('never promotes the answers of a calibration queue', async () => {
    const calls = serveCalibration('calibrate')
    renderAt(
      '/queues/q1/calibration',
      '/queues/:queueId/calibration',
      <CalibrationPage />,
    )
    await screen.findByRole('group', { name: 'Reviewers against each other' })

    press('g')

    expect(
      screen.queryByRole('region', { name: 'Promote to gold' }),
    ).not.toBeInTheDocument()
    expect(promotions(calls)).toEqual([])
  })
})

describe('GoldSetsPage', () => {
  it('shows a set with its version, newest items and conflicts, and moves with J', async () => {
    const calls = fakeApi([
      [
        'GET',
        /^\/api\/v1\/gold-sets$/,
        () => ({
          items: [
            { ...TRIAGE_GOLD, version: 3, item_count: 2 },
            { ...TOPICS_GOLD, version: 2, item_count: 1 },
          ],
        }),
      ],
      [
        'GET',
        /^\/api\/v1\/gold-sets\/triage-gold$/,
        () => ({
          ...TRIAGE_GOLD,
          version: 3,
          item_count: 2,
          sources: [{ queue_id: 'q1' }],
          content_hash_matches: true,
          recent_additions: [
            item('ticket-2', 'bug'),
            item('ticket-1', 'refund'),
          ],
          duplicates: [],
          conflicts: [
            {
              item_id: 'item-ticket-1',
              fields: ['intent'],
              gold: item('ticket-1', 'refund'),
              other: item('ticket-1', 'other'),
            },
          ],
        }),
      ],
      [
        'GET',
        /^\/api\/v1\/gold-sets\/topics-gold$/,
        () => ({
          ...TOPICS_GOLD,
          version: 2,
          item_count: 1,
          sources: [],
          content_hash_matches: false,
          recent_additions: [],
          duplicates: [],
          conflicts: [],
        }),
      ],
    ])
    render(
      <QueryClientProvider client={client()}>
        <MemoryRouter initialEntries={['/gold']}>
          <Routes>
            <Route path="/gold" element={<GoldSetsPage />} />
            <Route path="/gold/:goldSetId" element={<GoldSetsPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(
      await screen.findByRole('heading', { name: 'Triage gold' }),
    ).toBeVisible()
    expect(screen.getByTestId('gold-version')).toHaveTextContent('version 3')
    expect(screen.getByTestId('gold-item-count')).toHaveTextContent('2 items')
    expect(
      screen.getAllByTestId('gold-item').map((row) => row.textContent),
    ).toEqual([
      expect.stringContaining('ticket-2intent bug'),
      expect.stringContaining('ticket-1intent refund'),
    ])
    expect(screen.getByTestId('gold-conflict')).toHaveTextContent(
      'intent refund, and intent other',
    )

    press('j')

    expect(
      await screen.findByRole('heading', { name: 'Topics gold' }),
    ).toBeVisible()
    expect(screen.getByRole('status')).toHaveTextContent(
      'gold.jsonl is not the file version 2 describes',
    )
    expect(calls.map((c) => c.path)).toContain('/api/v1/gold-sets/topics-gold')
  })
})
