import { useState } from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RubricForm } from './rubric-form'
import { rubricFields, type Labels } from './rubric'

const TOPICS = Array.from({ length: 12 }, (_, i) => `topic-${String(i + 1)}`)

const fields = rubricFields([
  {
    name: 'topic',
    field_type: 'categorical',
    required: true,
    options: TOPICS,
  },
  {
    name: 'score',
    field_type: 'numeric',
    required: true,
    scale_min: 0,
    scale_max: 10,
  },
])

function Form() {
  const [labels, setLabels] = useState<Labels>({})
  const [active, setActive] = useState(0)
  return (
    <RubricForm
      fields={fields}
      labels={labels}
      onChange={setLabels}
      active={active}
      onActivate={setActive}
    />
  )
}

describe('RubricForm', () => {
  it('offers every option of a long choice field, not only the keyed nine', () => {
    render(<Form />)
    const topic = screen.getByRole('group', { name: 'topic' })
    expect(within(topic).getAllByRole('button')).toHaveLength(12)

    const last = within(topic).getByRole('button', { name: 'topic-12' })
    fireEvent.click(last)
    expect(last).toHaveAttribute('aria-pressed', 'true')
  })

  it('keeps an input on a numeric scale, and offers both of its ends', () => {
    render(<Form />)
    const input = screen.getByRole('spinbutton', { name: 'score' })
    const scale = screen.getByRole('group', { name: 'score' })

    fireEvent.click(within(scale).getByRole('button', { name: '10' }))
    expect(input).toHaveValue(10)
    fireEvent.click(within(scale).getByRole('button', { name: '0' }))
    expect(input).toHaveValue(0)

    fireEvent.change(input, { target: { value: '7' } })
    expect(within(scale).getByRole('button', { name: '7' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })
})
