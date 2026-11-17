import { describe, expect, it } from 'vitest'
import type { DisagreementDetail } from '@/api/generated/types.gen'
import { rubricFields } from '@/features/review/rubric'
import { agentSources, agreedLabels, sourcesOf, take } from './resolution'

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

  it('maps each field still holding an AI value to that proposal', () => {
    const [ada, , ai] = sourcesOf(detail)
    if (!ada || !ai) throw new Error('expected three columns')
    const settled = agreedLabels(fields, detail)
    const fromAi = take(fields, settled, ai, null)

    expect(agentSources(fields, fromAi, { intent: ai, urgent: ai })).toEqual({
      intent: 'o1',
      urgent: 'o1',
    })
    expect(
      agentSources(
        fields,
        { ...fromAi, intent: 'bug' },
        { intent: ai, urgent: ai },
      ),
    ).toEqual({ urgent: 'o1' })
    expect(agentSources(fields, fromAi, { intent: ada })).toEqual({})
  })

  it('claims no field whose AI value is empty', () => {
    const withNote = rubricFields([
      { name: 'intent', field_type: 'categorical', options: ['refund', 'bug'] },
      { name: 'note', field_type: 'text' },
      { name: 'tags', field_type: 'multi_select', options: ['a', 'b'] },
    ])
    const empty = {
      ...detail,
      agent_labels: [
        {
          agent_output_id: 'o1',
          agent_run_id: 'run1',
          labels: { intent: 'refund', note: '', tags: [] },
        },
      ],
    }
    const ai = sourcesOf(empty)[2]
    if (!ai) throw new Error('expected an AI column')
    const fromAi = take(withNote, {}, ai, null)

    expect(
      agentSources(withNote, fromAi, { intent: ai, note: ai, tags: ai }),
    ).toEqual({ intent: 'o1' })
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
