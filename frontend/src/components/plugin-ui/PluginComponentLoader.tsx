/**
 * Tier 2 — Dynamic plugin component loader (PL-015).
 *
 * Loads plugin-provided React component bundles via dynamic import.
 * Plugin components are pre-built ES module files (.mjs) placed in
 * `workbench/plugins/{pluginId}/ui/`.
 *
 * Features:
 * - Dynamic import with React.lazy
 * - Error boundary wrapping (broken plugins cannot crash the app)
 * - Versioned import paths (atomic plugin-version updates)
 * - Loading state with Suspense fallback
 * - Typed props contracts via the plugin SDK types
 *
 * See PRD section 17.5.2 for specification.
 */

import { Suspense, lazy, useMemo } from "react"

import { PluginErrorBoundary } from "./PluginErrorBoundary"
import type { PluginComponentManifest } from "@/types/plugin-ui"

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PluginComponentLoaderProps {
  /** Manifest describing the component to load. */
  manifest: PluginComponentManifest
  /** Props to pass to the loaded component. */
  componentProps: Record<string, unknown>
  /** Optional loading fallback. */
  loadingFallback?: React.ReactNode
  /** Called when the plugin component encounters an error. */
  onError?: (error: Error, pluginId: string) => void
}

// ---------------------------------------------------------------------------
// Import path construction
// ---------------------------------------------------------------------------

/**
 * Build the import URL for a plugin component bundle.
 *
 * Plugin bundles live at:
 *   /workbench/plugins/{pluginId}/ui/{bundlePath}
 *
 * The version is appended as a query parameter for cache busting,
 * ensuring atomic plugin-version updates.
 */
function buildImportPath(manifest: PluginComponentManifest): string {
  const basePath = `/workbench/plugins/${manifest.pluginId}/ui/${manifest.bundlePath}`
  return `${basePath}?v=${manifest.pluginVersion}`
}

// ---------------------------------------------------------------------------
// Component cache
// ---------------------------------------------------------------------------

/**
 * Cache of lazy-loaded components keyed by pluginId + version + slot.
 *
 * This ensures that the same plugin component is not loaded multiple
 * times, and that version changes trigger a fresh import.
 */
const componentCache = new Map<string, React.LazyExoticComponent<React.ComponentType<Record<string, unknown>>>>()

function getCacheKey(manifest: PluginComponentManifest): string {
  return `${manifest.pluginId}@${manifest.pluginVersion}:${manifest.slot}`
}

function getOrCreateLazyComponent(
  manifest: PluginComponentManifest,
): React.LazyExoticComponent<React.ComponentType<Record<string, unknown>>> {
  const key = getCacheKey(manifest)
  const cached = componentCache.get(key)
  if (cached) return cached

  const importPath = buildImportPath(manifest)
  const LazyComponent = lazy(async () => {
    try {
      const module = await import(/* @vite-ignore */ importPath) as {
        default: React.ComponentType<Record<string, unknown>>
      }
      if (!module.default) {
        throw new Error(
          `Plugin bundle "${importPath}" does not have a default export. ` +
            `Plugin components must use "export default".`,
        )
      }
      return module
    } catch (error) {
      console.error(
        `[MoLabel] Failed to load plugin component: ${manifest.pluginId}`,
        error,
      )
      throw error
    }
  })

  componentCache.set(key, LazyComponent)
  return LazyComponent
}

// ---------------------------------------------------------------------------
// Loading fallback
// ---------------------------------------------------------------------------

function DefaultLoadingFallback() {
  return (
    <div className="flex items-center justify-center p-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
        Loading plugin component...
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * Dynamically loads and renders a plugin React component.
 *
 * This component handles the full lifecycle of loading a plugin's
 * custom React component:
 *
 * 1. Constructs a versioned import path from the manifest
 * 2. Uses React.lazy for code splitting and dynamic loading
 * 3. Wraps the component in a Suspense boundary (loading state)
 * 4. Wraps the component in an error boundary (crash protection)
 * 5. Caches loaded components to avoid duplicate imports
 *
 * Plugin components receive all data through props and must not
 * import from the core app bundle.
 */
export function PluginComponentLoader({
  manifest,
  componentProps,
  loadingFallback,
  onError,
}: PluginComponentLoaderProps) {
  const LazyComponent = useMemo(
    () => getOrCreateLazyComponent(manifest),
    [manifest],
  )

  const errorBoundaryProps = {
    pluginId: manifest.pluginId,
    pluginVersion: manifest.pluginVersion,
    ...(onError ? { onError } : {}),
  }

  return (
    <PluginErrorBoundary {...errorBoundaryProps}>
      <Suspense fallback={loadingFallback ?? <DefaultLoadingFallback />}>
        <LazyComponent {...componentProps} />
      </Suspense>
    </PluginErrorBoundary>
  )
}

// ---------------------------------------------------------------------------
// Utility: invalidate cached component for a plugin
// ---------------------------------------------------------------------------

/**
 * Remove a plugin's cached component, forcing a fresh import on next render.
 *
 * Call this after a plugin update to ensure the new version is loaded.
 */
export function invalidatePluginComponent(
  pluginId: string,
  slot?: string,
): void {
  for (const key of componentCache.keys()) {
    if (key.startsWith(pluginId)) {
      if (!slot || key.endsWith(`:${slot}`)) {
        componentCache.delete(key)
      }
    }
  }
}

/**
 * Clear the entire plugin component cache.
 *
 * Useful during development or after a full plugin system refresh.
 */
export function clearPluginComponentCache(): void {
  componentCache.clear()
}
