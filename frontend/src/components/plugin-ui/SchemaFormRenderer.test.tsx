/**
 * Tests for SchemaFormRenderer (PL-014 Tier 1).
 */

import { render, screen, fireEvent } from "@testing-library/react"
import { describe, it, expect, vi } from "vitest"

import { SchemaFormRenderer } from "./SchemaFormRenderer"
import type { FormSchema } from "@/types/plugin-ui"

// ---------------------------------------------------------------------------
// Test schemas
// ---------------------------------------------------------------------------

const simpleSchema: FormSchema = {
  type: "object",
  title: "Test Form",
  description: "A test form",
  properties: {
    name: {
      type: "string",
      title: "Name",
      description: "Enter your name",
    },
    age: {
      type: "integer",
      title: "Age",
    },
    active: {
      type: "boolean",
      title: "Active",
    },
  },
  required: ["name"],
}

const enumSchema: FormSchema = {
  type: "object",
  properties: {
    sentiment: {
      type: "string",
      title: "Sentiment",
      enum: ["positive", "negative", "neutral"],
    },
  },
}

const radioSchema: FormSchema = {
  type: "object",
  properties: {
    choice: {
      type: "string",
      title: "Choice",
      enum: ["A", "B", "C"],
      "x-widget": "radio",
    },
  },
}

const textareaSchema: FormSchema = {
  type: "object",
  properties: {
    notes: {
      type: "string",
      title: "Notes",
      "x-widget": "textarea",
      "x-placeholder": "Enter notes...",
    },
  },
}

const sliderSchema: FormSchema = {
  type: "object",
  properties: {
    score: {
      type: "number",
      title: "Score",
      minimum: 0,
      maximum: 100,
      "x-widget": "slider",
    },
  },
}

const hiddenSchema: FormSchema = {
  type: "object",
  properties: {
    visible: { type: "string", title: "Visible" },
    secret: { type: "string", title: "Secret", "x-widget": "hidden" },
  },
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SchemaFormRenderer", () => {
  it("renders form title and description", () => {
    render(
      <SchemaFormRenderer
        schema={simpleSchema}
        values={{}}
        onChange={() => {}}
      />,
    )
    expect(screen.getByText("Test Form")).toBeInTheDocument()
    expect(screen.getByText("A test form")).toBeInTheDocument()
  })

  it("renders string field with label and description", () => {
    render(
      <SchemaFormRenderer
        schema={simpleSchema}
        values={{ name: "Alice" }}
        onChange={() => {}}
      />,
    )
    expect(screen.getByText("Name")).toBeInTheDocument()
    expect(screen.getByText("Enter your name")).toBeInTheDocument()
    expect(screen.getByDisplayValue("Alice")).toBeInTheDocument()
  })

  it("marks required fields with asterisk", () => {
    render(
      <SchemaFormRenderer
        schema={simpleSchema}
        values={{}}
        onChange={() => {}}
      />,
    )
    // The "Name" label should have a "*" sibling
    const nameLabel = screen.getByText("Name")
    expect(nameLabel.parentElement?.textContent).toContain("*")
  })

  it("calls onChange when a text field value changes", () => {
    const onChange = vi.fn()
    render(
      <SchemaFormRenderer
        schema={simpleSchema}
        values={{ name: "Alice" }}
        onChange={onChange}
      />,
    )
    const input = screen.getByDisplayValue("Alice")
    fireEvent.change(input, { target: { value: "Bob" } })
    expect(onChange).toHaveBeenCalledWith("name", "Bob")
  })

  it("renders number field", () => {
    render(
      <SchemaFormRenderer
        schema={simpleSchema}
        values={{ age: 25 }}
        onChange={() => {}}
      />,
    )
    expect(screen.getByDisplayValue("25")).toBeInTheDocument()
  })

  it("renders boolean field as checkbox", () => {
    const onChange = vi.fn()
    render(
      <SchemaFormRenderer
        schema={simpleSchema}
        values={{ active: false }}
        onChange={onChange}
      />,
    )
    const checkbox = screen.getByRole("checkbox")
    expect(checkbox).not.toBeChecked()
    fireEvent.click(checkbox)
    expect(onChange).toHaveBeenCalledWith("active", true)
  })

  it("renders enum field as select dropdown", () => {
    render(
      <SchemaFormRenderer
        schema={enumSchema}
        values={{ sentiment: "positive" }}
        onChange={() => {}}
      />,
    )
    const select = screen.getByDisplayValue("positive")
    expect(select).toBeInTheDocument()
  })

  it("renders radio widget for enum fields", () => {
    render(
      <SchemaFormRenderer
        schema={radioSchema}
        values={{ choice: "B" }}
        onChange={() => {}}
      />,
    )
    const radios = screen.getAllByRole("radio")
    expect(radios).toHaveLength(3)
    // B should be checked
    expect(radios[1]).toBeChecked()
  })

  it("renders textarea widget", () => {
    render(
      <SchemaFormRenderer
        schema={textareaSchema}
        values={{ notes: "Some text" }}
        onChange={() => {}}
      />,
    )
    expect(screen.getByDisplayValue("Some text")).toBeInTheDocument()
    expect(screen.getByPlaceholderText("Enter notes...")).toBeInTheDocument()
  })

  it("renders slider widget", () => {
    render(
      <SchemaFormRenderer
        schema={sliderSchema}
        values={{ score: 50 }}
        onChange={() => {}}
      />,
    )
    const slider = screen.getByRole("slider")
    expect(slider).toBeInTheDocument()
  })

  it("hides fields with x-widget: hidden", () => {
    render(
      <SchemaFormRenderer
        schema={hiddenSchema}
        values={{ visible: "yes", secret: "hidden" }}
        onChange={() => {}}
      />,
    )
    expect(screen.getByText("Visible")).toBeInTheDocument()
    expect(screen.queryByText("Secret")).not.toBeInTheDocument()
  })

  it("respects readOnly prop", () => {
    render(
      <SchemaFormRenderer
        schema={simpleSchema}
        values={{ name: "Alice" }}
        onChange={() => {}}
        readOnly
      />,
    )
    const input = screen.getByDisplayValue("Alice")
    expect(input).toHaveAttribute("readOnly")
  })

  it("sorts fields by x-order", () => {
    const orderedSchema: FormSchema = {
      type: "object",
      properties: {
        last: { type: "string", title: "Last", "x-order": 2 },
        first: { type: "string", title: "First", "x-order": 1 },
      },
    }
    render(
      <SchemaFormRenderer
        schema={orderedSchema}
        values={{}}
        onChange={() => {}}
      />,
    )
    const labels = screen.getAllByText(/First|Last/)
    expect(labels[0]?.textContent).toBe("First")
    expect(labels[1]?.textContent).toBe("Last")
  })
})
