import { formatValue } from './rubric'

const TEXT_KEYS = new Set(['text', 'content', 'body'])

function recordFields(view: Record<string, unknown> | null | undefined) {
  const payload = view?.payload
  const stable = view?.stable_fields
  const merged = {
    ...(typeof stable === 'object' && stable !== null ? stable : {}),
    ...(typeof payload === 'object' && payload !== null ? payload : {}),
  } as Record<string, unknown>
  return Object.entries(merged).filter(([key]) => !TEXT_KEYS.has(key))
}

/** The record as the reviewer reads it: its text, then its other fields. */
export function RecordView({
  item,
}: {
  item: {
    record_text?: string | null
    record_view?: Record<string, unknown> | null
  }
}) {
  const fields = recordFields(item.record_view)
  return (
    <div className="mt-3">
      {item.record_text ? (
        <p
          data-testid="record-text"
          className="max-w-[68ch] font-serif text-[1.35rem] leading-relaxed text-pretty text-ink"
        >
          {item.record_text}
        </p>
      ) : (
        <p className="text-sm text-faint">This record has no text field.</p>
      )}
      {fields.length > 0 && (
        <dl className="mt-6 grid max-w-[68ch] grid-cols-[auto_1fr] gap-x-6 gap-y-1 border-t border-rule pt-3 text-sm">
          {fields.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="font-mono text-xs leading-6 text-faint">{key}</dt>
              <dd className="leading-6 break-words text-ink-soft">
                {formatValue(value)}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}
