/**
 * Tier 1 — JSON-schema-driven column renderer (PL-014).
 *
 * Renders table cell content based on plugin-declared column definitions.
 * Used by the data explorer's TanStack Table integration to display
 * record fields according to the column type.
 */

import type { ColumnDefinition, ColumnRenderType } from '@/types/plugin-ui'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface SchemaColumnRendererProps {
  /** The column definition from the plugin. */
  column: ColumnDefinition
  /** The raw cell value extracted from the record. */
  value: unknown
}

// ---------------------------------------------------------------------------
// Cell renderers by column type
// ---------------------------------------------------------------------------

function toDisplayText(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean')
    return String(value)
  if (value instanceof Date) return value.toISOString()
  return JSON.stringify(value)
}

function renderText(value: unknown): React.ReactNode {
  if (value == null) return <span className="text-muted-foreground">--</span>
  const text = toDisplayText(value)
  // Truncate long text to keep table rows compact
  if (text.length > 120) {
    return <span title={text}>{text.slice(0, 117)}...</span>
  }
  return <span>{text}</span>
}

function renderNumber(value: unknown): React.ReactNode {
  if (value == null) return <span className="text-muted-foreground">--</span>
  const num = Number(value)
  if (Number.isNaN(num))
    return <span className="text-muted-foreground">NaN</span>
  // Format with reasonable precision
  const formatted = Number.isInteger(num) ? String(num) : num.toFixed(3)
  return <span className="tabular-nums">{formatted}</span>
}

function renderBadge(value: unknown): React.ReactNode {
  if (value == null) return null
  const text = toDisplayText(value)
  return (
    <span className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2">
      {text}
    </span>
  )
}

function renderProgress(value: unknown): React.ReactNode {
  if (value == null) return null
  const num = Number(value)
  if (Number.isNaN(num)) return null
  // Assume value is 0-1 or 0-100
  const pct = num > 1 ? num : num * 100
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${String(Math.min(100, Math.max(0, pct)))}%` }}
        />
      </div>
      <span className="min-w-[3ch] text-right text-xs tabular-nums text-muted-foreground">
        {Math.round(pct)}%
      </span>
    </div>
  )
}

function renderDate(value: unknown): React.ReactNode {
  if (value == null) return <span className="text-muted-foreground">--</span>
  try {
    const date = new Date(toDisplayText(value))
    return (
      <time dateTime={date.toISOString()} className="tabular-nums">
        {date.toLocaleDateString(undefined, {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
        })}
      </time>
    )
  } catch {
    return <span>{toDisplayText(value)}</span>
  }
}

function renderJson(value: unknown): React.ReactNode {
  if (value == null) return <span className="text-muted-foreground">null</span>
  const json = JSON.stringify(value, null, 0)
  const truncated = json.length > 80 ? json.slice(0, 77) + '...' : json
  return (
    <code
      className="rounded bg-muted px-1 py-0.5 font-mono text-xs"
      title={json}
    >
      {truncated}
    </code>
  )
}

function renderBoolean(value: unknown): React.ReactNode {
  if (value == null) return <span className="text-muted-foreground">--</span>
  const bool = Boolean(value)
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        bool ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
      }`}
    >
      {bool ? 'Yes' : 'No'}
    </span>
  )
}

const RENDERERS: Record<ColumnRenderType, (value: unknown) => React.ReactNode> =
  {
    text: renderText,
    number: renderNumber,
    badge: renderBadge,
    progress: renderProgress,
    date: renderDate,
    json: renderJson,
    boolean: renderBoolean,
  }

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * Renders a single table cell based on a plugin column definition.
 *
 * Used by the data explorer to generically render plugin-declared
 * columns. Each column's `columnType` determines the rendering style.
 */
export function SchemaColumnRenderer({
  column,
  value,
}: SchemaColumnRendererProps) {
  const renderFn = RENDERERS[column.columnType ?? 'text']
  return <>{renderFn(value)}</>
}

// ---------------------------------------------------------------------------
// Utility: extract a nested value from a record using a dot-path key
// ---------------------------------------------------------------------------

/**
 * Extract a value from a record using a dot-separated field path.
 *
 * @example
 * extractFieldValue({ stable_fields: { sentiment: "positive" } }, "stable_fields.sentiment")
 * // => "positive"
 */
export function extractFieldValue(
  record: Record<string, unknown>,
  fieldPath: string,
): unknown {
  const parts = fieldPath.split('.')
  let current: unknown = record
  for (const part of parts) {
    if (current == null || typeof current !== 'object') return undefined
    current = (current as Record<string, unknown>)[part]
  }
  return current
}
