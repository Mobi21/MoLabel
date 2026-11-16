import { describe, expect, it } from 'vitest'
import {
  missingRequired,
  parseLabels,
  pickValue,
  rubricFields,
  submission,
} from './rubric'

const fields = rubricFields([
  {
    name: 'intent',
    field_type: 'categorical',
    required: true,
    options: ['refund', 'bug', 'shipping', 'other'],
  },
  { name: 'urgent', field_type: 'bool', required: true },
  {
    name: 'tags',
    field_type: 'multi_select',
    required: false,
    options: ['billing', 'account'],
  },
  { name: 'note', field_type: 'text', required: false },
])
const [intent, urgent, tags] = fields as [
  (typeof fields)[number],
  (typeof fields)[number],
  (typeof fields)[number],
]
const proposal = { intent: 'refund', urgent: false, tags: [], note: '' }

describe('submission', () => {
  it('accepts with the proposal as sent when nothing changed', () => {
    const outcome = submission(fields, parseLabels(fields, proposal), proposal)
    expect(outcome.decision).toBe('accept')
    expect(outcome.labels).toBe(proposal)
  })

  it('treats a cleared empty text or list as unchanged', () => {
    const outcome = submission(
      fields,
      { intent: 'refund', urgent: false },
      proposal,
    )
    expect(outcome.decision).toBe('accept')
  })

  it('edits, naming the changed fields, when a value differs', () => {
    const form = { ...parseLabels(fields, proposal), urgent: true }
    const outcome = submission(fields, form, proposal)
    expect(outcome.decision).toBe('edit')
    expect(outcome.changed).toEqual(['urgent'])
    expect(outcome.labels).toEqual(form)
  })

  it('sends labels with no decision when no proposal was shown', () => {
    const outcome = submission(fields, { intent: 'bug' }, null)
    expect(outcome).toEqual({
      decision: null,
      labels: { intent: 'bug' },
      changed: [],
    })
  })
})

describe('pickValue', () => {
  it('sets the nth option on a choice and yes or no on a bool', () => {
    expect(pickValue(intent, {}, 3)).toEqual({ intent: 'shipping' })
    expect(pickValue(urgent, {}, 1)).toEqual({ urgent: true })
    expect(pickValue(urgent, {}, 2)).toEqual({ urgent: false })
  })

  it('toggles a multi-select option, keeping option order', () => {
    const both = pickValue(tags, { tags: ['account'] }, 1)
    expect(both).toEqual({ tags: ['billing', 'account'] })
    expect(pickValue(tags, both ?? {}, 2)).toEqual({ tags: ['billing'] })
  })

  it('ignores a key past the last option', () => {
    expect(pickValue(intent, {}, 5)).toBeNull()
    expect(pickValue(urgent, {}, 3)).toBeNull()
  })
})

describe('missingRequired', () => {
  it('names required fields without a value; false counts as a value', () => {
    expect(missingRequired(fields, { urgent: false })).toEqual(['intent'])
    expect(missingRequired(fields, { intent: 'bug', urgent: false })).toEqual(
      [],
    )
  })
})
