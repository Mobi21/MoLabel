import { NavLink } from 'react-router-dom'
import type { QueueSummary } from '@/api/generated/types.gen'
import { cn } from '@/lib/utils'
import { isAdjudicable, isBlind, kindLabel, queueTitle } from './queues'

const SCREENS = [
  { path: 'review', label: 'Review' },
  { path: 'adjudication', label: 'Adjudicate' },
  { path: 'calibration', label: 'Calibration' },
] as const

/** The queue's name, its screens, and the reviewer's progress in it. */
export function QueueHeader({
  queueId,
  queue,
}: {
  queueId: string
  queue: QueueSummary | undefined
}) {
  const mine = queue?.my_submitted ?? 0
  const left = queue?.my_remaining ?? 0
  return (
    <div className="border-b border-rule bg-sheet/60">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-end gap-x-8 gap-y-3 px-6 pt-5">
        <div className="min-w-0 pb-3">
          <p className="font-mono text-[11px] text-faint">
            <NavLink to="/" className="hover:text-ink">
              Queues
            </NavLink>{' '}
            / {queueId.slice(0, 8)}
          </p>
          <h1 className="mt-1 flex items-center gap-2 text-lg font-semibold tracking-tight">
            {queue ? queueTitle(queue) : 'Queue'}
            {queue && (
              <span className="rounded-[3px] border border-rule px-1.5 py-px font-mono text-[11px] font-normal text-ink-soft">
                {kindLabel(queue)}
              </span>
            )}
            {queue && isBlind(queue) && (
              <span className="rounded-[3px] border border-signal/40 px-1.5 py-px font-mono text-[11px] font-normal text-signal">
                blind
              </span>
            )}
          </h1>
        </div>
        <nav aria-label="Queue screens" className="flex gap-1 self-end">
          {SCREENS.filter(
            (screen) =>
              screen.path !== 'adjudication' || !queue || isAdjudicable(queue),
          ).map((screen) => (
            <NavLink
              key={screen.path}
              to={`/queues/${queueId}/${screen.path}`}
              className={({ isActive }) =>
                cn(
                  '-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors',
                  isActive
                    ? 'border-signal text-ink'
                    : 'border-transparent text-ink-soft hover:text-ink',
                )
              }
            >
              {screen.label}
            </NavLink>
          ))}
        </nav>
        {queue && (
          <p className="ml-auto pb-3 font-mono text-xs text-ink-soft tabular-nums">
            you {mine} done · {left} left
          </p>
        )}
      </div>
    </div>
  )
}
