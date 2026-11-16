import type { DisagreementDetail } from '@/api/generated/types.gen'
import {
  parseLabels,
  type Labels,
  type RawLabels,
  type RubricField,
} from '@/features/review/rubric'

const SOURCE_LETTERS = ['a', 'b', 'c', 'd'] as const

/** One column of the side-by-side view: a reviewer, or an agent proposal. */
export interface Source {
  letter: (typeof SOURCE_LETTERS)[number] | null
  name: string
  kind: 'reviewer' | 'agent'
  labels: RawLabels
  decision: string | null
}

export function sourcesOf(detail: DisagreementDetail): Source[] {
  const columns: Omit<Source, 'letter'>[] = [
    ...detail.reviewer_labels.map((set) => ({
      name: set.reviewer_name,
      kind: 'reviewer' as const,
      labels: set.labels,
      decision: set.decision ?? null,
    })),
    ...detail.agent_labels.map((set) => ({
      name: 'AI proposal',
      kind: 'agent' as const,
      labels: set.labels,
      decision: null,
    })),
  ]
  return columns.map((column, index) => ({
    ...column,
    letter: SOURCE_LETTERS[index] ?? null,
  }))
}

/** The fields every reviewer agrees on, already settled. */
export function agreedLabels(
  fields: readonly RubricField[],
  detail: DisagreementDetail,
): Labels {
  const conflicts = new Set(detail.fields_in_conflict)
  const first = detail.reviewer_labels[0]
  const settled = fields.filter((field) => !conflicts.has(field.name))
  return parseLabels(settled, first?.labels)
}

/** Take a source's value for one field, or for every field. */
export function take(
  fields: readonly RubricField[],
  labels: Labels,
  source: Source,
  only: string | null,
): Labels {
  const picked = parseLabels(
    only === null ? fields : fields.filter((f) => f.name === only),
    source.labels,
  )
  return { ...labels, ...picked }
}
