/**
 * Plugin UI type definitions.
 *
 * Defines the typed props contracts for plugin-provided React components
 * (Tier 2) and the JSON schema structures for generic rendering (Tier 1).
 *
 * See PRD sections 17.5.1 and 17.5.2 for specification.
 */

// ---------------------------------------------------------------------------
// JSON Schema types for Tier 1 generic rendering
// ---------------------------------------------------------------------------

/** JSON Schema field type for form rendering. */
export type SchemaFieldType =
  | 'string'
  | 'number'
  | 'integer'
  | 'boolean'
  | 'array'
  | 'object'

/** UI widget hint for form field rendering. */
export type FieldWidget =
  | 'text'
  | 'textarea'
  | 'select'
  | 'radio'
  | 'checkbox'
  | 'slider'
  | 'number'
  | 'date'
  | 'json'
  | 'hidden'
  | 'multi-select'

/** A single property in a JSON schema form definition. */
export interface SchemaProperty {
  type: SchemaFieldType
  title?: string
  description?: string
  default?: unknown
  enum?: readonly string[]
  minimum?: number
  maximum?: number
  minLength?: number
  maxLength?: number
  pattern?: string
  items?: SchemaProperty
  properties?: Record<string, SchemaProperty>
  required?: readonly string[]
  /** UI rendering hint, not part of JSON Schema standard. */
  'x-widget'?: FieldWidget
  /** Display order hint. */
  'x-order'?: number
  /** Whether the field is read-only. */
  'x-readonly'?: boolean
  /** Placeholder text for input fields. */
  'x-placeholder'?: string
}

/**
 * JSON Schema used by plugins to declare form fields.
 * The core renders this generically using SchemaFormRenderer.
 */
export interface FormSchema {
  type: 'object'
  title?: string
  description?: string
  properties: Record<string, SchemaProperty>
  required?: readonly string[]
}

// ---------------------------------------------------------------------------
// Column definitions for Tier 1 table rendering
// ---------------------------------------------------------------------------

/** Render type for table columns. */
export type ColumnRenderType =
  | 'text'
  | 'number'
  | 'badge'
  | 'progress'
  | 'date'
  | 'json'
  | 'boolean'

/** Column definition declared by plugins for data explorer table views. */
export interface ColumnDefinition {
  /** Field path to extract from the record, e.g. "stable_fields.sentiment". */
  key: string
  /** Display header text. */
  label: string
  /** Render type. */
  columnType?: ColumnRenderType
  /** Preferred width in pixels (undefined = auto). */
  width?: number
  /** Whether the column is sortable. */
  sortable?: boolean
  /** Whether the column is filterable. */
  filterable?: boolean
}

// ---------------------------------------------------------------------------
// Layout definitions for Tier 1 layout rendering
// ---------------------------------------------------------------------------

/** Section type within a layout. */
export type LayoutSectionType =
  | 'fields'
  | 'json'
  | 'text'
  | 'markdown'
  | 'custom'

/** A single section within a detail or review layout. */
export interface LayoutSection {
  sectionId: string
  title: string
  sectionType: LayoutSectionType
  /** Field paths to display (for "fields" section type). */
  fields?: readonly string[]
  /** Additional configuration for the section. */
  config?: Record<string, unknown>
  /** Whether the section is initially collapsed. */
  collapse?: boolean
}

/** Full layout specification for detail or review screens. */
export interface LayoutSpec {
  sections: readonly LayoutSection[]
  sidebar?: readonly LayoutSection[]
}

// ---------------------------------------------------------------------------
// Tier 2 — Typed props contracts for plugin React components
// ---------------------------------------------------------------------------

/** Record data passed to plugin components. */
export interface PluginRecord {
  id: string
  datasetId: string
  externalId?: string
  stableFields: Record<string, unknown>
  payload: Record<string, unknown>
  recordKind?: string
}

/** Label field definition passed to plugin components. */
export interface PluginLabelField {
  name: string
  fieldType: string
  required: boolean
  options?: readonly string[]
  scaleMin?: number
  scaleMax?: number
  description: string
  default?: unknown
}

/** Task schema information passed to plugin components. */
export interface PluginTaskSchema {
  id: string
  taskType: string
  title: string
  labelFields: readonly PluginLabelField[]
  requiredFields: readonly string[]
  instructions?: string
}

/** Review state information passed to plugin components. */
export interface PluginReviewState {
  currentLabels: Record<string, unknown>
  previousLabels?: Record<string, unknown>
  agentLabels?: Record<string, unknown>
  isAgentRevealed: boolean
  reviewStartedAt: string
}

/**
 * Props contract for plugin record renderer components.
 *
 * Used in the review screen's left pane and the detail inspector.
 * Plugin components receive all record data through these props and
 * must NOT import from the core app bundle.
 */
export interface PluginRecordRendererProps {
  record: PluginRecord
  taskSchema: PluginTaskSchema
  /** Layout mode: "review" for review screen, "detail" for inspector. */
  mode: 'review' | 'detail'
}

/**
 * Props contract for plugin review form components.
 *
 * Replaces the generic JSON-schema form on the right pane of the review
 * screen. The plugin component is responsible for rendering label inputs
 * and calling onSubmit when the user submits their review.
 */
export interface PluginReviewFormProps {
  record: PluginRecord
  taskSchema: PluginTaskSchema
  reviewState: PluginReviewState
  /** Called when the user changes a label value. */
  onLabelChange: (fieldName: string, value: unknown) => void
  /** Called when the user submits the review. */
  onSubmit: (labels: Record<string, unknown>, decision: string) => void
  /** Called when the user skips the record. */
  onSkip: () => void
}

/**
 * Props contract for plugin detail panel components.
 *
 * Renders a custom panel within the record detail inspector.
 */
export interface PluginDetailPanelProps {
  record: PluginRecord
  taskSchema: PluginTaskSchema
  /** Panel-specific configuration from the plugin manifest. */
  config?: Record<string, unknown>
}

/**
 * Props contract for plugin dashboard panel components.
 *
 * Renders a custom dashboard widget in the project overview.
 */
export interface PluginDashboardPanelProps {
  /** Panel data computed by the backend DashboardPanelPlugin. */
  data: Record<string, unknown>
  /** Panel configuration from the workspace manifest. */
  config?: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// Plugin component manifest (Tier 2 loading metadata)
// ---------------------------------------------------------------------------

/** Component slot identifiers for plugin UI bundles. */
export type PluginComponentSlot =
  | 'record_renderer'
  | 'review_form'
  | 'detail_panel'
  | 'dashboard_panel'
  | 'custom_screen'

/**
 * Metadata for a dynamically loaded plugin component bundle.
 *
 * The core uses this to construct the import path and wrap the component
 * in an error boundary.
 */
export interface PluginComponentManifest {
  /** Plugin identifier. */
  pluginId: string
  /** Plugin version (for atomic version updates). */
  pluginVersion: string
  /** Which UI slot this component fills. */
  slot: PluginComponentSlot
  /**
   * Relative path to the ES module bundle within the plugin's UI directory.
   * Full path: workbench/plugins/{pluginId}/ui/{bundlePath}
   */
  bundlePath: string
}
