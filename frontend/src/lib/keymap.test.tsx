import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { letter, modEnter, plainKey, useKeymap, type Binding } from './keymap'

function Harness({ bindings }: { bindings: Binding[] }) {
  useKeymap(bindings)
  return (
    <>
      <button type="button">Native</button>
      <textarea aria-label="Note" />
    </>
  )
}

function binding(id: string, match: Binding['match'], extra = {}): Binding {
  return { id, caps: [id], label: id, match, run: vi.fn(), ...extra }
}

describe('useKeymap', () => {
  it('runs the first enabled binding that matches', () => {
    const skip = binding('s', letter('s'), { disabled: true })
    const also = binding('s2', letter('s'))
    render(<Harness bindings={[skip, also]} />)
    fireEvent.keyDown(document.body, { key: 's' })
    expect(skip.run).not.toHaveBeenCalled()
    expect(also.run).toHaveBeenCalledOnce()
  })

  it('leaves letters to a focused text field, but not modifier chords marked inText', () => {
    const next = binding('j', letter('j'))
    const submit = binding('submit', modEnter, { inText: true })
    render(<Harness bindings={[next, submit]} />)
    const note = screen.getByRole('textbox', { name: 'Note' })
    fireEvent.keyDown(note, { key: 'j' })
    fireEvent.keyDown(note, { key: 'Enter', ctrlKey: true })
    expect(next.run).not.toHaveBeenCalled()
    expect(submit.run).toHaveBeenCalledOnce()
  })

  it('lets Enter activate a focused button instead of the screen binding', () => {
    const enter = binding('enter', plainKey('Enter'))
    render(<Harness bindings={[enter]} />)
    fireEvent.keyDown(screen.getByRole('button', { name: 'Native' }), {
      key: 'Enter',
    })
    expect(enter.run).not.toHaveBeenCalled()
    fireEvent.keyDown(document.body, { key: 'Enter' })
    expect(enter.run).toHaveBeenCalledOnce()
  })
})
