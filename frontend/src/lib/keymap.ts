import { useLayoutEffect, useRef } from 'react'

/**
 * One keyboard action. A screen's bindings both handle keys and render the
 * on-screen legend, so the two cannot drift apart.
 */
export interface Binding {
  id: string
  /** Key caps shown in the legend, such as ['Ctrl', 'Enter']. */
  caps: readonly string[]
  label: string
  match: (event: KeyboardEvent) => boolean
  run: (event: KeyboardEvent) => void
  /** Fire while the focus is in a text field. */
  inText?: boolean
  disabled?: boolean
}

function hasModifier(event: KeyboardEvent): boolean {
  return event.ctrlKey || event.metaKey || event.altKey
}

export function plainKey(...keys: string[]) {
  const wanted = new Set(keys)
  return (event: KeyboardEvent) =>
    !hasModifier(event) && !event.shiftKey && wanted.has(event.key)
}

export function letter(char: string, { shift = false } = {}) {
  return (event: KeyboardEvent) =>
    !hasModifier(event) &&
    event.shiftKey === shift &&
    event.key.toLowerCase() === char
}

export function digitKey(event: KeyboardEvent): boolean {
  return !hasModifier(event) && /^[1-9]$/.test(event.key)
}

export function modEnter(event: KeyboardEvent): boolean {
  return (event.ctrlKey || event.metaKey) && event.key === 'Enter'
}

export const MOD = /Mac|iPhone|iPad/.test(navigator.userAgent) ? '⌘' : 'Ctrl'

export function isTextTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable || target instanceof HTMLTextAreaElement) {
    return true
  }
  return (
    target instanceof HTMLInputElement &&
    !['checkbox', 'radio', 'button', 'submit'].includes(target.type)
  )
}

/** A plain Enter or Space on a focused control activates that control. */
function activatesControl(event: KeyboardEvent): boolean {
  return (
    (event.key === 'Enter' || event.key === ' ') &&
    !hasModifier(event) &&
    event.target instanceof Element &&
    event.target.closest('a[href], button, [role="button"]') !== null
  )
}

/**
 * Run the first enabled binding that matches each key press on the window.
 *
 * Layout effects swap the listener and its bindings in the same commit as
 * the DOM, so a key pressed as soon as a new item shows never reaches the
 * bindings of the item it replaced.
 */
export function useKeymap(bindings: readonly Binding[]): void {
  const current = useRef(bindings)
  useLayoutEffect(() => {
    current.current = bindings
  })

  useLayoutEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.defaultPrevented || event.isComposing || event.repeat) return
      if (activatesControl(event)) return
      const typing = isTextTarget(event.target)
      const binding = current.current.find(
        (b) => !b.disabled && (!typing || b.inText) && b.match(event),
      )
      if (binding) {
        event.preventDefault()
        binding.run(event)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [])
}
