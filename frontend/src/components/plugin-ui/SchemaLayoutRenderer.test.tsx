/**
 * Tests for SchemaLayoutRenderer (PL-014 Tier 1).
 */

import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect } from 'vitest'

import { SchemaLayoutRenderer } from './SchemaLayoutRenderer'
import type { LayoutSpec } from '@/types/plugin-ui'

describe('SchemaLayoutRenderer', () => {
  it('renders fields section with labels and values', () => {
    const layout: LayoutSpec = {
      sections: [
        {
          sectionId: 'main',
          title: 'Main Fields',
          sectionType: 'fields',
          fields: ['name', 'email'],
        },
      ],
    }
    const data = { name: 'Alice', email: 'alice@example.com' }

    render(<SchemaLayoutRenderer layout={layout} data={data} />)
    expect(screen.getByText('Main Fields')).toBeInTheDocument()
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('alice@example.com')).toBeInTheDocument()
  })

  it('renders json section', () => {
    const layout: LayoutSpec = {
      sections: [
        {
          sectionId: 'raw',
          title: 'Raw Data',
          sectionType: 'json',
          config: { fieldPath: 'metadata' },
        },
      ],
    }
    const data = { metadata: { version: '1.0' } }

    render(<SchemaLayoutRenderer layout={layout} data={data} />)
    expect(screen.getByText('Raw Data')).toBeInTheDocument()
    // Check that JSON is rendered
    expect(screen.getByText(/"version": "1.0"/)).toBeInTheDocument()
  })

  it('renders text section', () => {
    const layout: LayoutSpec = {
      sections: [
        {
          sectionId: 'body',
          title: 'Body Text',
          sectionType: 'text',
          config: { fieldPath: 'content' },
        },
      ],
    }
    const data = { content: 'Hello world' }

    render(<SchemaLayoutRenderer layout={layout} data={data} />)
    expect(screen.getByText('Body Text')).toBeInTheDocument()
    expect(screen.getByText('Hello world')).toBeInTheDocument()
  })

  it('renders sidebar sections', () => {
    const layout: LayoutSpec = {
      sections: [
        {
          sectionId: 'main',
          title: 'Main',
          sectionType: 'fields',
          fields: ['name'],
        },
      ],
      sidebar: [
        {
          sectionId: 'meta',
          title: 'Metadata',
          sectionType: 'fields',
          fields: ['status'],
        },
      ],
    }
    const data = { name: 'Test', status: 'active' }

    render(<SchemaLayoutRenderer layout={layout} data={data} />)
    expect(screen.getByText('Main')).toBeInTheDocument()
    expect(screen.getByText('Metadata')).toBeInTheDocument()
    expect(screen.getByText('active')).toBeInTheDocument()
  })

  it('supports collapsible sections', () => {
    const layout: LayoutSpec = {
      sections: [
        {
          sectionId: 'collapsed',
          title: 'Hidden Section',
          sectionType: 'fields',
          fields: ['secret'],
          collapse: true,
        },
      ],
    }
    const data = { secret: 'hidden value' }

    render(<SchemaLayoutRenderer layout={layout} data={data} />)
    // Section title is visible but content is hidden
    expect(screen.getByText('Hidden Section')).toBeInTheDocument()
    expect(screen.queryByText('hidden value')).not.toBeInTheDocument()

    // Click to expand
    fireEvent.click(screen.getByText('Hidden Section'))
    expect(screen.getByText('hidden value')).toBeInTheDocument()
  })

  it('shows placeholder for null field values', () => {
    const layout: LayoutSpec = {
      sections: [
        {
          sectionId: 'main',
          title: 'Main',
          sectionType: 'fields',
          fields: ['missing'],
        },
      ],
    }

    render(<SchemaLayoutRenderer layout={layout} data={{}} />)
    expect(screen.getByText('--')).toBeInTheDocument()
  })

  it('renders custom section placeholder', () => {
    const layout: LayoutSpec = {
      sections: [
        {
          sectionId: 'custom-viz',
          title: 'Visualization',
          sectionType: 'custom',
          config: { component: 'MyChart' },
        },
      ],
    }

    render(<SchemaLayoutRenderer layout={layout} data={{}} />)
    expect(screen.getByText(/MyChart/)).toBeInTheDocument()
  })
})
