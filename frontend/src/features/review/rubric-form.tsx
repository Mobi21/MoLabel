import { Kbd } from '@/components/key-legend'
import { cn } from '@/lib/utils'
import {
  JsonDraft,
  choices,
  formatValue,
  isList,
  keyFor,
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

/** A JSON field as editable text, which keeps what the reviewer typed. */
function JsonInput({
  name,
  value,
  disabled,
  placeholder,
  textRef,
  onFocus,
  onChange,
}: {
  name: string
  value: LabelValue | undefined
  disabled: boolean
  placeholder: string
  textRef: (element: HTMLTextAreaElement | null) => void
  onFocus: () => void
  onChange: (draft: JsonDraft) => void
}) {
  const text =
    value instanceof JsonDraft
      ? value.text
      : value === undefined
        ? ''
        : JSON.stringify(value, null, 2)
  const error = value instanceof JsonDraft ? value.error : null
  return (
    <>
      <textarea
        ref={textRef}
        aria-label={name}
        aria-invalid={error !== null}
        disabled={disabled}
        value={text}
        spellCheck={false}
        onFocus={onFocus}
        onChange={(event) => {
          onChange(new JsonDraft(event.target.value))
        }}
        rows={Math.min(12, Math.max(3, text.split('\n').length))}
        placeholder={placeholder}
        className={cn(
          'mt-2 w-full resize-y rounded-[3px] border bg-paper px-2.5 py-1.5 font-mono text-xs placeholder:text-faint',
          error === null ? 'border-rule' : 'border-signal',
        )}
      />
      {error !== null && (
        <p className="mt-1 font-mono text-[11px] text-signal">
          Not valid JSON: {error}
        </p>
      )}
    </>
  )
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

/**
 * The task schema's fields as a rubric. Every value is a button or an input;
 * the keys 1 to 9 are shortcuts on the active field.
 */
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
        const value = labels[field.name]
        const values = choices(field)
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

            {field.kind === 'number' && (
              <input
                type="number"
                aria-label={field.name}
                min={field.min ?? undefined}
                max={field.max ?? undefined}
                disabled={disabled}
                value={typeof value === 'number' ? String(value) : ''}
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
            )}
            {field.kind === 'text' ? (
              <textarea
                ref={(element) => {
                  textRef?.(field.name, element)
                }}
                aria-label={field.name}
                disabled={disabled}
                value={typeof value === 'string' ? value : ''}
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
            ) : field.kind === 'json' ? (
              <JsonInput
                name={field.name}
                value={value}
                disabled={disabled}
                placeholder={isActive ? 'Enter to write, Esc to leave' : ''}
                textRef={(element) => {
                  textRef?.(field.name, element)
                }}
                onFocus={() => {
                  onActivate(index)
                }}
                onChange={(draft) => {
                  onChange({ ...labels, [field.name]: draft })
                }}
              />
            ) : (
              values.length > 0 && (
                <div
                  role="group"
                  aria-label={field.name}
                  className="mt-2 flex flex-wrap gap-1.5"
                >
                  {values.map((choice) => {
                    const picked = isPicked(field, labels, choice)
                    const text = formatValue(choice)
                    const key = keyFor(field, choice)
                    return (
                      <button
                        key={text}
                        type="button"
                        disabled={disabled}
                        aria-pressed={picked}
                        aria-keyshortcuts={
                          isActive && key !== null ? String(key) : undefined
                        }
                        title={descriptions[text]}
                        onClick={() => {
                          onActivate(index)
                          onChange(pickValue(field, labels, choice))
                        }}
                        className={cn(
                          'flex items-center gap-2 rounded-[3px] border px-2 py-1 text-sm transition-colors',
                          picked
                            ? 'border-ink bg-ink text-paper'
                            : 'border-rule bg-paper hover:border-ink-soft',
                        )}
                      >
                        {isActive && key !== null && (
                          <span aria-hidden>
                            <Kbd
                              className={cn(
                                picked &&
                                  'border-ink-soft bg-ink-soft text-paper',
                              )}
                            >
                              {String(key)}
                            </Kbd>
                          </span>
                        )}
                        {text}
                      </button>
                    )
                  })}
                </div>
              )
            )}
          </li>
        )
      })}
    </ol>
  )
}
