/**
 * Error boundary for dynamically loaded plugin components (PL-015).
 *
 * Wraps every plugin component so that a broken plugin cannot crash
 * the entire application. Displays a user-friendly error message
 * with the plugin identifier for debugging.
 */

import { Component } from "react"
import type { ErrorInfo, ReactNode } from "react"

// ---------------------------------------------------------------------------
// Props & State
// ---------------------------------------------------------------------------

export interface PluginErrorBoundaryProps {
  /** Plugin identifier for error reporting. */
  pluginId: string
  /** Plugin version for error reporting. */
  pluginVersion?: string
  /** Optional fallback UI. If not provided, a default error card is shown. */
  fallback?: ReactNode
  /** Called when an error is caught, for logging/telemetry. */
  onError?: (error: Error, pluginId: string) => void
  children: ReactNode
}

interface PluginErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * React error boundary that catches rendering errors from plugin components.
 *
 * When a plugin component throws during render, this boundary catches the
 * error and shows a fallback UI instead of crashing the app.
 */
export class PluginErrorBoundary extends Component<
  PluginErrorBoundaryProps,
  PluginErrorBoundaryState
> {
  constructor(props: PluginErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): PluginErrorBoundaryState {
    return { hasError: true, error }
  }

  override componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error(
      `[MoLabel] Plugin component error in "${this.props.pluginId}"` +
        (this.props.pluginVersion ? ` v${this.props.pluginVersion}` : ""),
      error,
      errorInfo,
    )
    this.props.onError?.(error, this.props.pluginId)
  }

  override render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }
      return (
        <div
          className="rounded-lg border border-destructive/50 bg-destructive/5 p-4"
          role="alert"
        >
          <h4 className="mb-1 text-sm font-semibold text-destructive">
            Plugin Error
          </h4>
          <p className="text-sm text-muted-foreground">
            The plugin component{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">
              {this.props.pluginId}
            </code>
            {this.props.pluginVersion && (
              <span> (v{this.props.pluginVersion})</span>
            )}{" "}
            encountered an error and could not render.
          </p>
          {this.state.error && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-muted-foreground">
                Error details
              </summary>
              <pre className="mt-1 overflow-auto rounded bg-muted p-2 font-mono text-xs">
                {this.state.error.message}
              </pre>
            </details>
          )}
        </div>
      )
    }

    return this.props.children
  }
}
