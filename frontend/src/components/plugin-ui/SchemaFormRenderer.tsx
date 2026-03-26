/**
 * Tier 1 — JSON-schema-driven form renderer (PL-014).
 *
 * Plugins declare their review/config forms via JSON schema. This component
 * renders the schema generically using standard HTML form elements styled
 * with Tailwind CSS (following shadcn/ui conventions).
 */

import { useCallback } from "react"

import type { FormSchema, SchemaProperty } from "@/types/plugin-ui"

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface SchemaFormRendererProps {
  /** The JSON schema describing the form fields. */
  schema: FormSchema
  /** Current form values keyed by field name. */
  values: Record<string, unknown>
  /** Called when any field value changes. */
  onChange: (fieldName: string, value: unknown) => void
  /** Whether the entire form is read-only. */
  readOnly?: boolean
}

// ---------------------------------------------------------------------------
// Field renderers
// ---------------------------------------------------------------------------

interface FieldProps {
  name: string
  property: SchemaProperty
  value: unknown
  onChange: (value: unknown) => void
  required: boolean
  readOnly: boolean
}

function StringField({ name, property, value, onChange, required, readOnly }: FieldProps) {
  const widget = property["x-widget"]

  if (widget === "textarea") {
    return (
      <textarea
        id={name}
        value={(value as string) ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={property["x-placeholder"]}
        required={required}
        readOnly={readOnly}
        minLength={property.minLength}
        maxLength={property.maxLength}
        className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        rows={4}
      />
    )
  }

  if (property.enum) {
    const widgetType = widget ?? "select"

    if (widgetType === "radio") {
      return (
        <div className="flex flex-col gap-2" role="radiogroup" aria-labelledby={`${name}-label`}>
          {property.enum.map((option) => (
            <label key={option} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name={name}
                value={option}
                checked={value === option}
                onChange={() => onChange(option)}
                disabled={readOnly}
                className="h-4 w-4 border-input"
              />
              {option}
            </label>
          ))}
        </div>
      )
    }

    return (
      <select
        id={name}
        value={(value as string) ?? ""}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        disabled={readOnly}
        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <option value="">Select...</option>
        {property.enum.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    )
  }

  return (
    <input
      id={name}
      type="text"
      value={(value as string) ?? ""}
      onChange={(e) => onChange(e.target.value)}
      placeholder={property["x-placeholder"]}
      required={required}
      readOnly={readOnly}
      minLength={property.minLength}
      maxLength={property.maxLength}
      pattern={property.pattern}
      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
    />
  )
}

function NumberField({ name, property, value, onChange, required, readOnly }: FieldProps) {
  const widget = property["x-widget"]

  if (widget === "slider") {
    return (
      <div className="flex items-center gap-3">
        <input
          id={name}
          type="range"
          value={(value as number) ?? property.minimum ?? 0}
          onChange={(e) => onChange(Number(e.target.value))}
          min={property.minimum}
          max={property.maximum}
          disabled={readOnly}
          className="w-full"
        />
        <span className="min-w-[3ch] text-right text-sm text-muted-foreground">
          {(value as number) ?? property.minimum ?? 0}
        </span>
      </div>
    )
  }

  return (
    <input
      id={name}
      type="number"
      value={(value as number) ?? ""}
      onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
      min={property.minimum}
      max={property.maximum}
      required={required}
      readOnly={readOnly}
      placeholder={property["x-placeholder"]}
      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
    />
  )
}

function BooleanField({ name, value, onChange, readOnly }: FieldProps) {
  return (
    <label className="flex items-center gap-2">
      <input
        id={name}
        type="checkbox"
        checked={(value as boolean) ?? false}
        onChange={(e) => onChange(e.target.checked)}
        disabled={readOnly}
        className="h-4 w-4 rounded border-input"
      />
      <span className="text-sm text-muted-foreground">Enabled</span>
    </label>
  )
}

function JsonField({ name, property, value, onChange, readOnly }: FieldProps) {
  const stringValue = typeof value === "string" ? value : JSON.stringify(value ?? null, null, 2)
  return (
    <textarea
      id={name}
      value={stringValue}
      onChange={(e) => {
        try {
          onChange(JSON.parse(e.target.value) as unknown)
        } catch {
          // Allow intermediate invalid JSON while typing
          onChange(e.target.value)
        }
      }}
      placeholder={property["x-placeholder"] ?? "Enter JSON..."}
      readOnly={readOnly}
      className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
      rows={6}
    />
  )
}

// ---------------------------------------------------------------------------
// Field wrapper with label and description
// ---------------------------------------------------------------------------

interface FormFieldProps {
  name: string
  property: SchemaProperty
  value: unknown
  onChange: (value: unknown) => void
  required: boolean
  readOnly: boolean
}

function FormField({ name, property, value, onChange, required, readOnly }: FormFieldProps) {
  const isHidden = property["x-widget"] === "hidden"
  if (isHidden) return null

  const isReadOnly = readOnly || (property["x-readonly"] ?? false)

  const fieldProps: FieldProps = {
    name,
    property,
    value,
    onChange,
    required,
    readOnly: isReadOnly,
  }

  let fieldElement: React.ReactNode
  switch (property.type) {
    case "string":
      fieldElement = <StringField {...fieldProps} />
      break
    case "number":
    case "integer":
      fieldElement = <NumberField {...fieldProps} />
      break
    case "boolean":
      fieldElement = <BooleanField {...fieldProps} />
      break
    case "object":
    case "array":
      fieldElement = <JsonField {...fieldProps} />
      break
    default:
      fieldElement = <StringField {...fieldProps} />
  }

  return (
    <div className="space-y-2">
      <label
        id={`${name}-label`}
        htmlFor={name}
        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
      >
        {property.title ?? name}
        {required && <span className="ml-1 text-destructive">*</span>}
      </label>
      {fieldElement}
      {property.description && (
        <p className="text-[0.8rem] text-muted-foreground">{property.description}</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * Renders a form from a JSON schema definition.
 *
 * Plugins declare their UI via JSON schema (Tier 1). This component
 * renders form fields generically, handling string, number, boolean,
 * enum/select, textarea, slider, and JSON/object field types.
 */
export function SchemaFormRenderer({
  schema,
  values,
  onChange,
  readOnly = false,
}: SchemaFormRendererProps) {
  const handleFieldChange = useCallback(
    (fieldName: string) => (value: unknown) => {
      onChange(fieldName, value)
    },
    [onChange],
  )

  // Sort fields by x-order, then by declaration order
  const sortedFields = Object.entries(schema.properties).sort(
    ([, a], [, b]) => (a["x-order"] ?? 999) - (b["x-order"] ?? 999),
  )

  const requiredSet = new Set(schema.required ?? [])

  return (
    <div className="space-y-6" role="form" aria-label={schema.title}>
      {schema.title && (
        <div className="space-y-1">
          <h3 className="text-lg font-semibold">{schema.title}</h3>
          {schema.description && (
            <p className="text-sm text-muted-foreground">{schema.description}</p>
          )}
        </div>
      )}
      {sortedFields.map(([name, property]) => (
        <FormField
          key={name}
          name={name}
          property={property}
          value={values[name]}
          onChange={handleFieldChange(name)}
          required={requiredSet.has(name)}
          readOnly={readOnly}
        />
      ))}
    </div>
  )
}
