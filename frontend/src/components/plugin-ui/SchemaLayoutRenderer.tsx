/**
 * Tier 1 — JSON-schema-driven layout renderer (PL-014).
 *
 * Renders detail inspector and review screen layouts based on
 * plugin-declared LayoutSpec definitions. Each section type
 * (fields, json, text, markdown, custom) has a dedicated renderer.
 */

import { useState } from "react"

import type { LayoutSection, LayoutSpec } from "@/types/plugin-ui"

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface SchemaLayoutRendererProps {
  /** The layout specification from the plugin. */
  layout: LayoutSpec
  /** The record data to render. */
  data: Record<string, unknown>
  /** Optional class name for the container. */
  className?: string
}

// ---------------------------------------------------------------------------
// Section renderers
// ---------------------------------------------------------------------------

function extractValue(data: Record<string, unknown>, fieldPath: string): unknown {
  const parts = fieldPath.split(".")
  let current: unknown = data
  for (const part of parts) {
    if (current == null || typeof current !== "object") return undefined
    current = (current as Record<string, unknown>)[part]
  }
  return current
}

function FieldsSection({
  section,
  data,
}: {
  section: LayoutSection
  data: Record<string, unknown>
}) {
  const fields = section.fields ?? []
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
      {fields.map((field) => {
        const value = extractValue(data, field)
        return (
          <div key={field} className="contents">
            <dt className="text-sm font-medium text-muted-foreground">{field}</dt>
            <dd className="text-sm">
              {value == null ? (
                <span className="text-muted-foreground">--</span>
              ) : typeof value === "object" ? (
                <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                  {JSON.stringify(value)}
                </code>
              ) : (
                String(value)
              )}
            </dd>
          </div>
        )
      })}
    </dl>
  )
}

function JsonSection({
  section,
  data,
}: {
  section: LayoutSection
  data: Record<string, unknown>
}) {
  const fieldPath = section.config?.["fieldPath"] as string | undefined
  const jsonData = fieldPath ? extractValue(data, fieldPath) : data
  return (
    <pre className="overflow-auto rounded-md bg-muted p-4 font-mono text-xs">
      {JSON.stringify(jsonData, null, 2)}
    </pre>
  )
}

function TextSection({ section, data }: { section: LayoutSection; data: Record<string, unknown> }) {
  const fieldPath = section.config?.["fieldPath"] as string | undefined
  const text = fieldPath ? String(extractValue(data, fieldPath) ?? "") : ""
  return <p className="whitespace-pre-wrap text-sm">{text}</p>
}

function MarkdownSection({
  section,
  data,
}: {
  section: LayoutSection
  data: Record<string, unknown>
}) {
  const fieldPath = section.config?.["fieldPath"] as string | undefined
  const content = fieldPath ? String(extractValue(data, fieldPath) ?? "") : ""
  // Simple markdown rendering — for full markdown support, plugins should
  // use a Tier 2 custom component with a proper markdown library.
  return (
    <div className="prose prose-sm max-w-none dark:prose-invert">
      <pre className="whitespace-pre-wrap font-sans text-sm">{content}</pre>
    </div>
  )
}

function CustomSection({ section }: { section: LayoutSection }) {
  const componentName = section.config?.["component"] as string | undefined
  return (
    <div className="rounded-md border border-dashed border-muted-foreground/25 p-4 text-center text-sm text-muted-foreground">
      Custom component: {componentName ?? section.sectionId}
      <br />
      <span className="text-xs">Use Tier 2 dynamic loading for custom sections</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Collapsible section wrapper
// ---------------------------------------------------------------------------

function SectionWrapper({
  section,
  children,
}: {
  section: LayoutSection
  children: React.ReactNode
}) {
  const [isOpen, setIsOpen] = useState(!section.collapse)

  return (
    <div className="rounded-lg border bg-card text-card-foreground shadow-sm">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between p-4 text-left"
        aria-expanded={isOpen}
      >
        <h4 className="text-sm font-semibold">{section.title}</h4>
        <span
          className="text-muted-foreground transition-transform"
          style={{ transform: isOpen ? "rotate(180deg)" : "rotate(0deg)" }}
          aria-hidden
        >
          &#9660;
        </span>
      </button>
      {isOpen && <div className="border-t px-4 py-3">{children}</div>}
    </div>
  )
}

function renderSection(section: LayoutSection, data: Record<string, unknown>): React.ReactNode {
  switch (section.sectionType) {
    case "fields":
      return <FieldsSection section={section} data={data} />
    case "json":
      return <JsonSection section={section} data={data} />
    case "text":
      return <TextSection section={section} data={data} />
    case "markdown":
      return <MarkdownSection section={section} data={data} />
    case "custom":
      return <CustomSection section={section} />
    default:
      return null
  }
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * Renders a layout from a plugin-declared LayoutSpec.
 *
 * Supports main sections and an optional sidebar. Each section is
 * rendered according to its type: fields, json, text, markdown, or
 * custom (placeholder for Tier 2 dynamic components).
 */
export function SchemaLayoutRenderer({
  layout,
  data,
  className,
}: SchemaLayoutRendererProps) {
  const hasSidebar = layout.sidebar && layout.sidebar.length > 0

  return (
    <div className={`flex gap-6 ${className ?? ""}`}>
      {/* Main content */}
      <div className={`flex flex-col gap-4 ${hasSidebar ? "flex-1" : "w-full"}`}>
        {layout.sections.map((section) => (
          <SectionWrapper key={section.sectionId} section={section}>
            {renderSection(section, data)}
          </SectionWrapper>
        ))}
      </div>

      {/* Sidebar */}
      {hasSidebar && (
        <aside className="flex w-80 flex-col gap-4">
          {layout.sidebar?.map((section) => (
            <SectionWrapper key={section.sectionId} section={section}>
              {renderSection(section, data)}
            </SectionWrapper>
          ))}
        </aside>
      )}
    </div>
  )
}
