import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { meQuery } from '@/api/queries'
import { fakeApi } from '@/test/fake-api'
import { CalibrationPage } from './calibration-page'

function scope(alpha: number) {
  return {
    pooled: {
      krippendorff_alpha: alpha,
      percent_agreement: 0.9,
      comparisons: 6,
    },
    fields: {
      intent: {
        krippendorff_alpha: alpha,
        percent_agreement: 0.9,
        comparisons: 6,
      },
    },
    skipped_fields: {},
  }
}

function renderCalibration() {
  fakeApi([
    ['GET', /^\/api\/v1\/queues$/, () => ({ items: [] })],
    [
      'GET',
      /^\/api\/v1\/quality\/agreement$/,
      () => ({
        workspace_id: 'w1',
        queue_id: 'q1',
        record_count: 6,
        reviewer_count: 2,
        inter_annotator: scope(0.7),
        human_agent: scope(0.95),
        warnings: [],
      }),
    ],
  ])
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
      <MemoryRouter initialEntries={['/queues/q1/calibration']}>
        <Routes>
          <Route
            path="/queues/:queueId/calibration"
            element={<CalibrationPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('CalibrationPage', () => {
  it('labels the human-vs-AI agreement as including accepts of shown proposals', async () => {
    renderCalibration()

    const humanAgent = await screen.findByRole('group', {
      name: 'Reviewers against the AI proposal',
    })
    const inter = screen.getByRole('group', {
      name: 'Reviewers against each other',
    })

    expect(
      within(humanAgent).getByText('includes accepts of shown proposals'),
    ).toBeVisible()
    expect(
      within(inter).queryByText('includes accepts of shown proposals'),
    ).toBeNull()
  })
})
