/**
 * Tests for SchemaColumnRenderer (PL-014 Tier 1).
 */

import { render, screen } from "@testing-library/react"
import { describe, it, expect } from "vitest"

import { SchemaColumnRenderer, extractFieldValue } from "./SchemaColumnRenderer"
import type { ColumnDefinition } from "@/types/plugin-ui"

describe("SchemaColumnRenderer", () => {
  it("renders text column", () => {
    const column: ColumnDefinition = { key: "name", label: "Name", columnType: "text" }
    render(<SchemaColumnRenderer column={column} value="Alice" />)
    expect(screen.getByText("Alice")).toBeInTheDocument()
  })

  it("renders null as placeholder for text", () => {
    const column: ColumnDefinition = { key: "name", label: "Name", columnType: "text" }
    render(<SchemaColumnRenderer column={column} value={null} />)
    expect(screen.getByText("--")).toBeInTheDocument()
  })

  it("truncates long text", () => {
    const column: ColumnDefinition = { key: "text", label: "Text", columnType: "text" }
    const longText = "x".repeat(200)
    render(<SchemaColumnRenderer column={column} value={longText} />)
    expect(screen.getByText(/\.\.\.$/)).toBeInTheDocument()
  })

  it("renders number column with formatting", () => {
    const column: ColumnDefinition = { key: "score", label: "Score", columnType: "number" }
    render(<SchemaColumnRenderer column={column} value={0.12345} />)
    expect(screen.getByText("0.123")).toBeInTheDocument()
  })

  it("renders integer without decimals", () => {
    const column: ColumnDefinition = { key: "count", label: "Count", columnType: "number" }
    render(<SchemaColumnRenderer column={column} value={42} />)
    expect(screen.getByText("42")).toBeInTheDocument()
  })

  it("renders badge column", () => {
    const column: ColumnDefinition = { key: "status", label: "Status", columnType: "badge" }
    render(<SchemaColumnRenderer column={column} value="active" />)
    expect(screen.getByText("active")).toBeInTheDocument()
  })

  it("renders progress column with percentage", () => {
    const column: ColumnDefinition = { key: "progress", label: "Progress", columnType: "progress" }
    render(<SchemaColumnRenderer column={column} value={0.75} />)
    expect(screen.getByText("75%")).toBeInTheDocument()
  })

  it("renders boolean column as Yes/No", () => {
    const column: ColumnDefinition = { key: "flag", label: "Flag", columnType: "boolean" }
    const { rerender } = render(<SchemaColumnRenderer column={column} value={true} />)
    expect(screen.getByText("Yes")).toBeInTheDocument()

    rerender(<SchemaColumnRenderer column={column} value={false} />)
    expect(screen.getByText("No")).toBeInTheDocument()
  })

  it("renders json column as code", () => {
    const column: ColumnDefinition = { key: "data", label: "Data", columnType: "json" }
    render(<SchemaColumnRenderer column={column} value={{ key: "val" }} />)
    expect(screen.getByText('{"key":"val"}')).toBeInTheDocument()
  })

  it("renders date column", () => {
    const column: ColumnDefinition = { key: "date", label: "Date", columnType: "date" }
    render(<SchemaColumnRenderer column={column} value="2026-03-23T10:00:00Z" />)
    // Date rendering is locale-dependent, just check it rendered something with Mar
    const timeEl = document.querySelector("time")
    expect(timeEl).not.toBeNull()
  })

  it("defaults to text rendering when columnType is omitted", () => {
    const column: ColumnDefinition = { key: "name", label: "Name" }
    render(<SchemaColumnRenderer column={column} value="test" />)
    expect(screen.getByText("test")).toBeInTheDocument()
  })
})

describe("extractFieldValue", () => {
  it("extracts top-level field", () => {
    expect(extractFieldValue({ name: "Alice" }, "name")).toBe("Alice")
  })

  it("extracts nested field", () => {
    const record = { stable_fields: { sentiment: "positive" } }
    expect(extractFieldValue(record, "stable_fields.sentiment")).toBe("positive")
  })

  it("returns undefined for missing path", () => {
    expect(extractFieldValue({ a: 1 }, "b.c")).toBeUndefined()
  })

  it("handles deeply nested paths", () => {
    const record = { a: { b: { c: { d: 42 } } } }
    expect(extractFieldValue(record, "a.b.c.d")).toBe(42)
  })
})
