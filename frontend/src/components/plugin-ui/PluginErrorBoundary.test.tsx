/**
 * Tests for PluginErrorBoundary (PL-015 Tier 2).
 */

import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import { PluginErrorBoundary } from './PluginErrorBoundary'

// Component that always throws during render
function ThrowingComponent(): never {
  throw new Error('Plugin render error')
}

// Component that renders normally
function GoodComponent() {
  return <div>Plugin content</div>
}

describe('PluginErrorBoundary', () => {
  // Suppress console.error for expected error boundary catches
  const originalConsoleError = console.error
  beforeEach(() => {
    console.error = vi.fn()
  })
  afterEach(() => {
    console.error = originalConsoleError
  })

  it('renders children when no error occurs', () => {
    render(
      <PluginErrorBoundary pluginId="test.plugin">
        <GoodComponent />
      </PluginErrorBoundary>,
    )
    expect(screen.getByText('Plugin content')).toBeInTheDocument()
  })

  it('catches render errors and shows default fallback', () => {
    render(
      <PluginErrorBoundary pluginId="test.broken">
        <ThrowingComponent />
      </PluginErrorBoundary>,
    )
    expect(screen.getByText('Plugin Error')).toBeInTheDocument()
    expect(screen.getByText(/test\.broken/)).toBeInTheDocument()
  })

  it('shows plugin version in error display when provided', () => {
    render(
      <PluginErrorBoundary pluginId="test.broken" pluginVersion="1.2.3">
        <ThrowingComponent />
      </PluginErrorBoundary>,
    )
    expect(screen.getByText(/v1\.2\.3/)).toBeInTheDocument()
  })

  it('shows custom fallback when provided', () => {
    render(
      <PluginErrorBoundary
        pluginId="test.broken"
        fallback={<div>Custom error message</div>}
      >
        <ThrowingComponent />
      </PluginErrorBoundary>,
    )
    expect(screen.getByText('Custom error message')).toBeInTheDocument()
    expect(screen.queryByText('Plugin Error')).not.toBeInTheDocument()
  })

  it('calls onError callback when error is caught', () => {
    const onError = vi.fn()
    render(
      <PluginErrorBoundary pluginId="test.broken" onError={onError}>
        <ThrowingComponent />
      </PluginErrorBoundary>,
    )
    expect(onError).toHaveBeenCalledWith(expect.any(Error), 'test.broken')
  })

  it('shows error details in expandable section', () => {
    render(
      <PluginErrorBoundary pluginId="test.broken">
        <ThrowingComponent />
      </PluginErrorBoundary>,
    )
    expect(screen.getByText('Error details')).toBeInTheDocument()
    expect(screen.getByText('Plugin render error')).toBeInTheDocument()
  })
})
