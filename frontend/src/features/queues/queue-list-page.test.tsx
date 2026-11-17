import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { QueueSummary } from '@/api/generated/types.gen'
import { meQuery } from '@/api/queries'
import { fakeApi } from '@/test/fake-api'
import { QueueHeader } from './queue-header'
import { QueueListPage } from './queue-list-page'

function queue(
  id: string,
  kind: NonNullable<QueueSummary['kind']>,
): QueueSummary {
  return {
    queue_id: id,
    workspace_id: 'w1',
    task_schema_id: 's1',
    task_schema_title: `Ticket triage ${id}`,
    kind,
    total: 4,
    available: 4,
    claimed: 0,
    submitted: 0,
    skipped: 0,
    my_remaining: 4,
    created_at: '2026-11-17T00:00:00Z',
  }
}

const REVIEW = queue('review-q', 'review')
const CALIBRATION = queue('calib-q', 'calibrate')

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

function renderQueues(items: QueueSummary[]) {
  fakeApi([['GET', /^\/api\/v1\/queues$/, () => ({ items })]])
  render(
    <QueryClientProvider client={client()}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<QueueListPage />} />
          <Route
            path="/queues/:queueId/:screen"
            element={<p>screen opened</p>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function screens(item: QueueSummary) {
  return within(
    screen.getByRole('navigation', {
      name: `${item.task_schema_title ?? ''} screens`,
    }),
  )
    .getAllByRole('link')
    .map((link) => link.textContent)
}

describe('QueueListPage', () => {
  it('offers no adjudication on a calibration queue', async () => {
    renderQueues([REVIEW, CALIBRATION])
    await screen.findAllByTestId('queue-row')

    expect(screens(REVIEW)).toEqual(['Review', 'Adjudicate', 'Calibration'])
    expect(screens(CALIBRATION)).toEqual(['Review', 'Calibration'])
  })

  it('does not open adjudication from the keyboard on a calibration queue', async () => {
    renderQueues([CALIBRATION, REVIEW])
    await screen.findAllByTestId('queue-row')

    fireEvent.keyDown(document.body, { key: 'd' })
    expect(screen.queryByText('screen opened')).toBeNull()

    fireEvent.keyDown(document.body, { key: 'j' })
    fireEvent.keyDown(document.body, { key: 'd' })
    expect(await screen.findByText('screen opened')).toBeVisible()
  })
})

describe('QueueHeader', () => {
  it('shows no adjudication tab on a calibration queue', () => {
    render(
      <MemoryRouter>
        <QueueHeader queueId="calib-q" queue={CALIBRATION} />
        <QueueHeader queueId="review-q" queue={REVIEW} />
      </MemoryRouter>,
    )

    const tabs = screen
      .getAllByRole('navigation', { name: 'Queue screens' })
      .map((nav) =>
        within(nav)
          .getAllByRole('link')
          .map((link) => link.textContent),
      )
    expect(tabs).toEqual([
      ['Review', 'Calibration'],
      ['Review', 'Adjudicate', 'Calibration'],
    ])
  })
})
