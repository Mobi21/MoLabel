import type { DisagreementDetail } from '@/api/generated/types.gen'
import {
  parseLabels,
  rawLabels,
  type LabelValue,
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
  /** The agent output an agent column shows, null for a reviewer. */
  agentOutputId: string | null
  labels: RawLabels
  decision: string | null
}

export function sourcesOf(detail: DisagreementDetail): Source[] {
  const columns: Omit<Source, 'letter'>[] = [
    ...detail.reviewer_labels.map((set) => ({
      name: set.reviewer_name,
      kind: 'reviewer' as const,
      agentOutputId: null,
      labels: set.labels,
      decision: set.decision ?? null,
    })),
    ...detail.agent_labels.map((set) => ({
      name: 'AI proposal',
      kind: 'agent' as const,
      agentOutputId: set.agent_output_id,
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

function sameValue(a: LabelValue, b: LabelValue | undefined): boolean {
  return (
    b !== undefined &&
    JSON.stringify(rawLabels({ value: a })) ===
      JSON.stringify(rawLabels({ value: b }))
  )
}

/** Null, "" and [] are no label, so taking one takes nothing from the AI. */
function isLabel(value: LabelValue): boolean {
  return (
    value !== null &&
    value !== '' &&
    !(Array.isArray(value) && value.length === 0)
  )
}

/**
 * Each field whose label still holds the value an agent proposal gave it,
 * mapped to that proposal. `taken` is the column each field was last taken
 * from.
 */
export function agentSources(
  fields: readonly RubricField[],
  labels: Labels,
  taken: Readonly<Record<string, Source>>,
): Record<string, string> {
  const sources: Record<string, string> = {}
  for (const field of fields) {
    const source = taken[field.name]
    if (!source?.agentOutputId) continue
    const value = parseLabels([field], source.labels)[field.name]
    if (
      value !== undefined &&
      isLabel(value) &&
      sameValue(value, labels[field.name])
    ) {
      sources[field.name] = source.agentOutputId
    }
  }
  return sources
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
