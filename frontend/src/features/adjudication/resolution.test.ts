import { describe, expect, it } from 'vitest'
import type { DisagreementDetail } from '@/api/generated/types.gen'
import { rubricFields } from '@/features/review/rubric'
import { agreedLabels, sourcesOf, take, takenProposals } from './resolution'

const fields = rubricFields([
  {
    name: 'intent',
    field_type: 'categorical',
    options: ['refund', 'bug', 'shipping', 'other'],
  },
  { name: 'urgent', field_type: 'bool' },
])

const detail: DisagreementDetail = {
  record_id: 'rec1',
  task_schema_id: 's1',
  dataset_id: 'd1',
  severity: 'low',
  adjudication_type: 'subjective',
  fields_in_conflict: ['intent'],
  reviewer_count: 2,
  status: 'pending',
  reviewer_labels: [
    {
      reviewer_id: 'r1',
      reviewer_name: 'Ada',
      review_event_id: 'e1',
      decision: 'edit',
      labels: { intent: 'other', urgent: true },
      created_at: '2026-11-16T00:00:00Z',
    },
    {
      reviewer_id: 'r2',
      reviewer_name: 'Grace',
      review_event_id: 'e2',
      decision: 'accept',
      labels: { intent: 'refund', urgent: true },
      created_at: '2026-11-16T00:00:01Z',
    },
  ],
  agent_labels: [
    {
      agent_output_id: 'o1',
      agent_run_id: 'run1',
      labels: { intent: 'refund', urgent: false },
    },
  ],
  disagreeing_fields: [],
}

describe('resolution', () => {
  it('letters the reviewers, then the AI proposal, as columns', () => {
    expect(sourcesOf(detail).map((s) => [s.letter, s.name])).toEqual([
      ['a', 'Ada'],
      ['b', 'Grace'],
      ['c', 'AI proposal'],
    ])
  })

  it('settles the fields the reviewers agree on and leaves conflicts open', () => {
    expect(agreedLabels(fields, detail)).toEqual({ urgent: true })
  })

  it('names the AI proposals whose taken values the labels still hold', () => {
    const [ada, , ai] = sourcesOf(detail)
    if (!ada || !ai) throw new Error('expected three columns')
    const settled = agreedLabels(fields, detail)
    const fromAi = take(fields, settled, ai, null)

    expect(takenProposals(fields, fromAi, { intent: ai, urgent: ai })).toEqual([
      'o1',
    ])
    expect(
      takenProposals(fields, { ...fromAi, intent: 'bug' }, { intent: ai }),
    ).toEqual([])
    expect(takenProposals(fields, fromAi, { intent: ada })).toEqual([])
  })

  it("takes one field or every field from a column's labels", () => {
    const [, grace, ai] = sourcesOf(detail)
    if (!grace || !ai) throw new Error('expected three columns')
    const settled = agreedLabels(fields, detail)
    expect(take(fields, settled, grace, 'intent')).toEqual({
      intent: 'refund',
      urgent: true,
    })
    expect(take(fields, settled, ai, null)).toEqual({
      intent: 'refund',
      urgent: false,
    })
  })
})
