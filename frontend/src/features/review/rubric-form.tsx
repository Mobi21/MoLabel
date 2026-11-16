import { Kbd } from '@/components/key-legend'
import { cn } from '@/lib/utils'
import {
  formatValue,
  isList,
  keyedValues,
  pickValue,
  withoutField,
  type LabelValue,
  type Labels,
  type RubricField,
} from './rubric'

interface RubricFormProps {
  fields: readonly RubricField[]
  labels: Labels
  onChange: (labels: Labels) => void
  active: number
  onActivate: (index: number) => void
  /** Fields whose value differs from the proposal or the reviewers. */
  marked?: ReadonlySet<string>
  disabled?: boolean
  textRef?: (name: string, element: HTMLTextAreaElement | null) => void
}

function isPicked(field: RubricField, labels: Labels, value: LabelValue) {
  const current = labels[field.name]
  if (field.kind === 'multi') {
    return (
      isList(current) && typeof value === 'string' && current.includes(value)
    )
  }
  return current === value
}

/** The task schema's fields as a rubric; the active field answers to 1 to 9. */
export function RubricForm({
  fields,
  labels,
  onChange,
  active,
  onActivate,
  marked,
  disabled = false,
  textRef,
}: RubricFormProps) {
  return (
    <ol className="divide-y divide-rule border-y border-rule">
      {fields.map((field, index) => {
        const isActive = index === active
        const values = keyedValues(field)
        const descriptions =
          field.kind === 'choice' || field.kind === 'multi'
            ? field.descriptions
            : {}
        return (
          <li
            key={field.name}
            data-testid={`field-${field.name}`}
            aria-current={isActive ? 'true' : undefined}
            className={cn(
              'relative border-l-2 py-3 pr-1 pl-4 transition-colors',
              isActive ? 'border-signal bg-sheet' : 'border-transparent',
            )}
          >
            <div className="flex items-baseline justify-between gap-3">
              <button
                type="button"
                disabled={disabled}
                onClick={() => {
                  onActivate(index)
                }}
                className="text-left"
              >
                <span className="font-mono text-sm font-medium">
                  {field.name}
                </span>
                {field.required && (
                  <span className="ml-1 text-signal" aria-label="required">
                    *
                  </span>
                )}
                {field.kind === 'multi' && (
                  <span className="ml-2 text-xs text-faint">pick any</span>
                )}
              </button>
              {marked?.has(field.name) && (
                <span className="font-mono text-[11px] text-signal">
                  changed
                </span>
              )}
            </div>
            {field.description && (
              <p className="mt-0.5 text-xs text-ink-soft">
                {field.description}
              </p>
            )}

            {field.kind === 'number' && values.length === 0 ? (
              <input
                type="number"
                aria-label={field.name}
                disabled={disabled}
                value={
                  typeof labels[field.name] === 'number'
                    ? String(labels[field.name])
                    : ''
                }
                onFocus={() => {
                  onActivate(index)
                }}
                onChange={(event) => {
                  onChange(
                    event.target.value === ''
                      ? withoutField(labels, field.name)
                      : { ...labels, [field.name]: Number(event.target.value) },
                  )
                }}
                className="mt-2 w-32 rounded-[3px] border border-rule bg-paper px-2.5 py-1 font-mono text-sm"
              />
            ) : field.kind === 'text' ? (
              <textarea
                ref={(element) => {
                  textRef?.(field.name, element)
                }}
                aria-label={field.name}
                disabled={disabled}
                value={
                  typeof labels[field.name] === 'string'
                    ? (labels[field.name] as string)
                    : ''
                }
                onFocus={() => {
                  onActivate(index)
                }}
                onChange={(event) => {
                  onChange({ ...labels, [field.name]: event.target.value })
                }}
                rows={2}
                placeholder={isActive ? 'Enter to write, Esc to leave' : ''}
                className="mt-2 w-full resize-y rounded-[3px] border border-rule bg-paper px-2.5 py-1.5 text-sm placeholder:text-faint"
              />
            ) : (
              <div
                role="group"
                aria-label={field.name}
                className="mt-2 flex flex-wrap gap-1.5"
              >
                {values.map((value, valueIndex) => {
                  const picked = isPicked(field, labels, value)
                  const text = formatValue(value)
                  return (
                    <button
                      key={text}
                      type="button"
                      disabled={disabled}
                      aria-pressed={picked}
                      title={descriptions[text]}
                      onClick={() => {
                        onActivate(index)
                        const next = pickValue(field, labels, valueIndex + 1)
                        if (next) onChange(next)
                      }}
                      className={cn(
                        'flex items-center gap-2 rounded-[3px] border px-2 py-1 text-sm transition-colors',
                        picked
                          ? 'border-ink bg-ink text-paper'
                          : 'border-rule bg-paper hover:border-ink-soft',
                      )}
                    >
                      {isActive && (
                        <Kbd
                          className={cn(
                            picked && 'border-ink-soft bg-ink-soft text-paper',
                          )}
                        >
                          {String(valueIndex + 1)}
                        </Kbd>
                      )}
                      {text}
                    </button>
                  )
                })}
              </div>
            )}
          </li>
        )
      })}
    </ol>
  )
}
