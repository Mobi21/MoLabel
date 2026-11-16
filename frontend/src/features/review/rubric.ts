import type { LabelFieldDef } from '@/api/generated/types.gen'

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | readonly JsonValue[]
  | { readonly [key: string]: JsonValue }

/** A JSON field's text as the reviewer typed it, and its value once it parses. */
export class JsonDraft {
  readonly value: JsonValue | undefined
  readonly error: string | null

  constructor(readonly text: string) {
    let value: JsonValue | undefined
    let error: string | null = null
    if (text.trim() !== '') {
      try {
        value = JSON.parse(text) as JsonValue
      } catch (cause) {
        error = cause instanceof Error ? cause.message : 'not valid JSON'
      }
    }
    this.value = value
    this.error = error
  }
}

export type LabelValue = JsonValue | JsonDraft
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
  | (FieldBase & { kind: 'json' })

/** A numeric scale shows a button per value up to this many values, as 0 to 10. */
const MAX_SCALE_BUTTONS = 11

/** The values a field offers as buttons. Every one is selectable by mouse. */
export function choices(field: RubricField): readonly LabelValue[] {
  switch (field.kind) {
    case 'choice':
    case 'multi':
      return field.options
    case 'bool':
      return [true, false]
    case 'number': {
      const { min, max } = field
      if (
        min === null ||
        max === null ||
        !Number.isInteger(min) ||
        !Number.isInteger(max) ||
        max - min + 1 > MAX_SCALE_BUTTONS
      ) {
        return []
      }
      return Array.from({ length: max - min + 1 }, (_, i) => min + i)
    }
    case 'text':
    case 'json':
      return []
  }
}

/** The value the key ``digit``, 1 to 9, picks on a field, if any. */
export function keyedValue(
  field: RubricField,
  digit: number,
): LabelValue | undefined {
  switch (field.kind) {
    case 'choice':
    case 'multi':
      return field.options[digit - 1]
    case 'bool':
      return [true, false][digit - 1]
    case 'number':
      return field.min !== null &&
        field.max !== null &&
        digit >= field.min &&
        digit <= field.max
        ? digit
        : undefined
    case 'text':
    case 'json':
      return undefined
  }
}

/** The key 1 to 9 that picks ``value`` on a field, or null when none does. */
export function keyFor(field: RubricField, value: LabelValue): number | null {
  for (let digit = 1; digit <= 9; digit++) {
    if (keyedValue(field, digit) === value) return digit
  }
  return null
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
      case 'json':
        return { ...base, kind: 'json' }
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
    case 'json':
      return raw === undefined || raw === null ? undefined : (raw as JsonValue)
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

function isUnset(field: RubricField, value: LabelValue | undefined): boolean {
  if (value === undefined) return true
  if (field.kind === 'json') {
    return value instanceof JsonDraft && value.text.trim() === ''
  }
  return value === '' || (isList(value) && value.length === 0)
}

export function withoutField(labels: Labels, name: string): Labels {
  return Object.fromEntries(Object.entries(labels).filter(([k]) => k !== name))
}

/** JSON text with object keys sorted, so equal values compare equal. */
function canonicalJson(value: LabelValue): string | undefined {
  const json = value instanceof JsonDraft ? value.value : value
  return JSON.stringify(json, (_key, v: unknown) =>
    v !== null && typeof v === 'object' && !Array.isArray(v)
      ? Object.fromEntries(
          Object.entries(v).sort(([a], [b]) => (a < b ? -1 : 1)),
        )
      : v,
  )
}

function sameValue(
  field: RubricField,
  a: LabelValue | undefined,
  b: LabelValue | undefined,
) {
  if (
    a === undefined ||
    b === undefined ||
    isUnset(field, a) ||
    isUnset(field, b)
  ) {
    return isUnset(field, a) && isUnset(field, b)
  }
  if (field.kind === 'json') {
    const invalid = (v: LabelValue) =>
      v instanceof JsonDraft && v.error !== null
    return !invalid(a) && !invalid(b) && canonicalJson(a) === canonicalJson(b)
  }
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
    .filter((field) => !sameValue(field, from[field.name], to[field.name]))
    .map((field) => field.name)
}

export function missingRequired(
  fields: readonly RubricField[],
  labels: Labels,
): string[] {
  return fields
    .filter((field) => field.required && isUnset(field, labels[field.name]))
    .map((field) => field.name)
}

/** The JSON fields whose text does not parse. */
export function invalidFields(
  fields: readonly RubricField[],
  labels: Labels,
): string[] {
  return fields
    .filter((field) => {
      const value = labels[field.name]
      return value instanceof JsonDraft && value.error !== null
    })
    .map((field) => field.name)
}

/** The labels to send, with each JSON field as its parsed value. */
export function rawLabels(labels: Labels): RawLabels {
  return Object.fromEntries(
    Object.entries(labels).flatMap(([name, value]) => {
      if (!(value instanceof JsonDraft)) return [[name, value]]
      return value.value === undefined ? [] : [[name, value.value]]
    }),
  )
}

/** Set a field's value, or toggle it on a multi-select. */
export function pickValue(
  field: RubricField,
  labels: Labels,
  value: LabelValue,
): Labels {
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

/** Pick the value key ``digit`` stands for, or null when it stands for none. */
export function pickKey(
  field: RubricField,
  labels: Labels,
  digit: number,
): Labels | null {
  const value = keyedValue(field, digit)
  return value === undefined ? null : pickValue(field, labels, value)
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
  if (proposal === null) {
    return { decision: null, labels: rawLabels(form), changed: [] }
  }
  const changed = changedFields(fields, parseLabels(fields, proposal), form)
  return changed.length === 0
    ? { decision: 'accept', labels: proposal, changed }
    : { decision: 'edit', labels: rawLabels(form), changed }
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
