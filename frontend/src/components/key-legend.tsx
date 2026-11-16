import { cn } from '@/lib/utils'
import type { Binding } from '@/lib/keymap'

export function Kbd({
  children,
  className,
}: {
  children: React.ReactNode
  className?: string
}) {
  return (
    <kbd
      className={cn(
        'inline-flex h-5 min-w-5 items-center justify-center rounded-[3px] border border-b-2 border-rule bg-sheet px-1 font-mono text-[11px] leading-none font-medium text-ink-soft',
        className,
      )}
    >
      {children}
    </kbd>
  )
}

/** The keys a screen answers to, rendered from the same bindings that handle them. */
export function KeyLegend({ bindings }: { bindings: readonly Binding[] }) {
  return (
    <footer
      aria-label="Keyboard shortcuts"
      className="fixed inset-x-0 bottom-0 z-10 border-t border-rule bg-paper/95 backdrop-blur-sm"
    >
      <ul className="mx-auto flex max-w-[1400px] flex-wrap gap-x-5 gap-y-1.5 px-6 py-2.5 text-xs text-ink-soft">
        {bindings.map((b) => (
          <li
            key={b.id}
            className={cn(
              'flex items-center gap-1.5',
              b.disabled && 'opacity-40',
            )}
          >
            <span className="flex items-center gap-0.5">
              {b.caps.map((cap) => (
                <Kbd key={cap}>{cap}</Kbd>
              ))}
            </span>
            <span>{b.label}</span>
          </li>
        ))}
      </ul>
    </footer>
  )
}
