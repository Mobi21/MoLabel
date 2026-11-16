import { describe, expect, it } from 'vitest'
import {
  JsonDraft,
  invalidFields,
  keyedValue,
  missingRequired,
  parseLabels,
  pickKey,
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

describe('pickKey', () => {
  it('sets the nth option on a choice and yes or no on a bool', () => {
    expect(pickKey(intent, {}, 3)).toEqual({ intent: 'shipping' })
    expect(pickKey(urgent, {}, 1)).toEqual({ urgent: true })
    expect(pickKey(urgent, {}, 2)).toEqual({ urgent: false })
  })

  it('toggles a multi-select option, keeping option order', () => {
    const both = pickKey(tags, { tags: ['account'] }, 1)
    expect(both).toEqual({ tags: ['billing', 'account'] })
    expect(pickKey(tags, both ?? {}, 2)).toEqual({ tags: ['billing'] })
  })

  it('ignores a key past the last option', () => {
    expect(pickKey(intent, {}, 5)).toBeNull()
    expect(pickKey(urgent, {}, 3)).toBeNull()
  })
})

describe('keyedValue', () => {
  it('keys the digit that is the value on a numeric scale', () => {
    const [score] = rubricFields([
      { name: 'score', field_type: 'numeric', scale_min: 3, scale_max: 7 },
    ])
    if (score === undefined) throw new Error('no field')
    expect(keyedValue(score, 1)).toBeUndefined()
    expect(keyedValue(score, 3)).toBe(3)
    expect(keyedValue(score, 7)).toBe(7)
    expect(keyedValue(score, 8)).toBeUndefined()
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

describe('a JSON field', () => {
  const json = rubricFields([
    {
      name: 'intent',
      field_type: 'categorical',
      required: false,
      options: ['refund', 'bug'],
    },
    { name: 'entities', field_type: 'json', required: true },
  ])
  const entities = [{ text: 'Ada', type: 'PERSON', span: [0, 3] }]
  const proposed = { intent: 'refund', entities }

  it('keeps arrays and objects from the API', () => {
    expect(parseLabels(json, proposed)).toEqual(proposed)
    expect(parseLabels(json, { entities: { a: 1 } })).toEqual({
      entities: { a: 1 },
    })
  })

  it('accepts when the typed JSON equals the proposal, whatever its key order', () => {
    const typed = new JsonDraft('[{"span":[0,3],"type":"PERSON","text":"Ada"}]')
    const outcome = submission(
      json,
      { intent: 'refund', entities: typed },
      proposed,
    )
    expect(outcome.decision).toBe('accept')
  })

  it('sends typed JSON parsed, as an edit when it differs', () => {
    const typed = new JsonDraft('[]')
    const outcome = submission(
      json,
      { intent: 'refund', entities: typed },
      proposed,
    )
    expect(outcome).toMatchObject({
      decision: 'edit',
      changed: ['entities'],
      labels: { intent: 'refund', entities: [] },
    })
    expect(missingRequired(json, { entities: typed })).toEqual([])
  })

  it('names a field whose text does not parse, and counts empty text as unset', () => {
    const labels = { entities: new JsonDraft('[{') }
    expect(invalidFields(json, labels)).toEqual(['entities'])
    expect(missingRequired(json, { entities: new JsonDraft('  ') })).toEqual([
      'entities',
    ])
  })
})
