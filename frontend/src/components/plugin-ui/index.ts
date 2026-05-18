/**
 * Plugin UI components — public API.
 *
 * Tier 1 (PL-014): JSON-schema-driven generic renderers.
 * Tier 2 (PL-015): Dynamic plugin component loader with error boundaries.
 */

// Tier 1 — Generic schema-driven renderers
export { SchemaFormRenderer } from './SchemaFormRenderer'
export type { SchemaFormRendererProps } from './SchemaFormRenderer'

export { SchemaColumnRenderer, extractFieldValue } from './SchemaColumnRenderer'
export type { SchemaColumnRendererProps } from './SchemaColumnRenderer'

export { SchemaLayoutRenderer } from './SchemaLayoutRenderer'
export type { SchemaLayoutRendererProps } from './SchemaLayoutRenderer'

// Tier 2 — Dynamic plugin component loader
export {
  PluginComponentLoader,
  invalidatePluginComponent,
  clearPluginComponentCache,
} from './PluginComponentLoader'
export type { PluginComponentLoaderProps } from './PluginComponentLoader'

export { PluginErrorBoundary } from './PluginErrorBoundary'
export type { PluginErrorBoundaryProps } from './PluginErrorBoundary'
