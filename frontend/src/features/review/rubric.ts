import type { LabelFieldDef } from '@/api/generated/types.gen'

export type LabelValue = string | boolean | number | readonly string[]
export type Labels = Readonly<Record<string, LabelValue>>
export type RawLabels = Readonly<Record<string, unknown>>

interface FieldBase {
  name: string
  required: boolean
  description: string
}

interface OptionField extends FieldBase {
  options: readonly string[]
  descriptions: Readonly<Record<string, string>>
}

export type RubricField =
  | (OptionField & { kind: 'choice' })
  | (OptionField & { kind: 'multi' })
  | (FieldBase & { kind: 'bool' })
  | (FieldBase & { kind: 'number'; min: number | null; max: number | null })
  | (FieldBase & { kind: 'text' })

/** The keys 1 to 9 pick these values, in order, on a field. */
export function keyedValues(field: RubricField): readonly LabelValue[] {
  switch (field.kind) {
    case 'choice':
    case 'multi':
      return field.options.slice(0, 9)
    case 'bool':
      return [true, false]
    case 'number': {
      if (field.min === null || field.max === null) return []
      const values: number[] = []
      for (let n = Math.max(1, field.min); n <= Math.min(9, field.max); n++) {
        if (Number.isInteger(n)) values.push(n)
      }
      return values
    }
    case 'text':
      return []
  }
}

export function rubricFields(defs: readonly LabelFieldDef[]): RubricField[] {
  return defs.map((def): RubricField => {
    const base = {
      name: def.name,
      required: def.required ?? true,
      description: def.description ?? '',
    }
    const options = {
      options: def.options ?? [],
      descriptions: def.option_descriptions ?? {},
    }
    switch (def.field_type) {
      case 'categorical':
      case 'ordinal':
        return { ...base, ...options, kind: 'choice' }
      case 'multi_select':
        return { ...base, ...options, kind: 'multi' }
      case 'bool':
        return { ...base, kind: 'bool' }
      case 'numeric':
        return {
          ...base,
          kind: 'number',
          min: def.scale_min ?? null,
          max: def.scale_max ?? null,
        }
      default:
        return { ...base, kind: 'text' }
    }
  })
}

function parseValue(field: RubricField, raw: unknown): LabelValue | undefined {
  switch (field.kind) {
    case 'choice':
    case 'text':
      return typeof raw === 'string' ? raw : undefined
    case 'multi':
      return Array.isArray(raw)
        ? raw.filter((v): v is string => typeof v === 'string')
        : undefined
    case 'bool':
      return typeof raw === 'boolean' ? raw : undefined
    case 'number':
      return typeof raw === 'number' ? raw : undefined
  }
}

/** Read the rubric's fields out of labels from the API. */
export function parseLabels(
  fields: readonly RubricField[],
  raw: RawLabels | null | undefined,
): Labels {
  const labels: Record<string, LabelValue> = {}
  for (const field of fields) {
    const value = parseValue(field, raw?.[field.name])
    if (value !== undefined) labels[field.name] = value
  }
  return labels
}

export function isList(value: unknown): value is readonly string[] {
  return Array.isArray(value)
}

function isUnset(value: LabelValue | undefined): boolean {
  return (
    value === undefined || value === '' || (isList(value) && value.length === 0)
  )
}

export function withoutField(labels: Labels, name: string): Labels {
  return Object.fromEntries(Object.entries(labels).filter(([k]) => k !== name))
}

function sameValue(a: LabelValue | undefined, b: LabelValue | undefined) {
  if (isUnset(a) || isUnset(b)) return isUnset(a) && isUnset(b)
  if (isList(a) && isList(b)) {
    return [...a].sort().join('\u0000') === [...b].sort().join('\u0000')
  }
  return a === b
}

export function changedFields(
  fields: readonly RubricField[],
  from: Labels,
  to: Labels,
): string[] {
  return fields
    .filter((field) => !sameValue(from[field.name], to[field.name]))
    .map((field) => field.name)
}

export function missingRequired(
  fields: readonly RubricField[],
  labels: Labels,
): string[] {
  return fields
    .filter((field) => field.required && isUnset(labels[field.name]))
    .map((field) => field.name)
}

/** Set the value key ``digit`` stands for on a field, or toggle it on a multi-select. */
export function pickValue(
  field: RubricField,
  labels: Labels,
  digit: number,
): Labels | null {
  const value = keyedValues(field)[digit - 1]
  if (value === undefined) return null
  if (field.kind === 'multi' && typeof value === 'string') {
    const current = labels[field.name]
    const picked = new Set(isList(current) ? current : [])
    if (picked.has(value)) picked.delete(value)
    else picked.add(value)
    return {
      ...labels,
      [field.name]: field.options.filter((o) => picked.has(o)),
    }
  }
  return { ...labels, [field.name]: value }
}

type Decision = 'accept' | 'edit' | 'reject'

export interface Submission {
  decision: Decision | null
  labels: RawLabels
  changed: readonly string[]
}

/**
 * What submitting the form means against the proposal the reviewer saw.
 *
 * Keeping every proposed value is an accept, which sends the proposal's
 * labels as they are. Changing any value is an edit. With no proposal shown,
 * as on a blind queue before reveal, there is nothing to accept or edit, so
 * the labels go with no decision.
 */
export function submission(
  fields: readonly RubricField[],
  form: Labels,
  proposal: RawLabels | null,
): Submission {
  if (proposal === null) return { decision: null, labels: form, changed: [] }
  const changed = changedFields(fields, parseLabels(fields, proposal), form)
  return changed.length === 0
    ? { decision: 'accept', labels: proposal, changed }
    : { decision: 'edit', labels: form, changed }
}

export function formatValue(value: unknown): string {
  if (value === undefined || value === null || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (Array.isArray(value)) {
    return value.length === 0 ? '—' : value.map(String).join(', ')
  }
  if (typeof value === 'string' || typeof value === 'number') {
    return String(value)
  }
  return JSON.stringify(value)
}
