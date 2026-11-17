import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { QueueSummary } from '@/api/generated/types.gen'
import { errorMessage } from '@/api/client'
import { KeyLegend } from '@/components/key-legend'
import { letter, plainKey, useKeymap, type Binding } from '@/lib/keymap'
import { cn } from '@/lib/utils'
import { isBlind, kindLabel, queueTitle, useQueues } from './queues'

function Meter({ done, total }: { done: number; total: number }) {
  const share = total === 0 ? 0 : done / total
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-rule"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={done}
    >
      <div
        className="h-full bg-ink transition-[width]"
        style={{ width: `${String(share * 100)}%` }}
      />
    </div>
  )
}

function QueueRow({
  queue,
  selected,
  onSelect,
}: {
  queue: QueueSummary
  selected: boolean
  onSelect: () => void
}) {
  const mine = queue.my_submitted ?? 0
  const left = queue.my_remaining ?? 0
  const base = `/queues/${queue.queue_id}`
  return (
    <li
      data-testid="queue-row"
      onFocusCapture={onSelect}
      className={cn(
        'grid grid-cols-[1fr_auto] gap-x-8 gap-y-3 border-l-2 border-transparent px-5 py-4 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_auto]',
        selected && 'border-signal bg-sheet',
      )}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="truncate text-base font-semibold">
            {queueTitle(queue)}
          </h2>
          <span className="rounded-[3px] border border-rule px-1.5 py-px font-mono text-[11px] text-ink-soft">
            {kindLabel(queue)}
          </span>
          {isBlind(queue) && (
            <span className="rounded-[3px] border border-signal/40 px-1.5 py-px font-mono text-[11px] text-signal">
              blind
            </span>
          )}
        </div>
        <p className="mt-1 font-mono text-[11px] text-faint">
          {queue.queue_id.slice(0, 8)} · opened{' '}
          {new Date(queue.created_at).toLocaleDateString()}
        </p>
      </div>
      <div className="col-span-2 space-y-1.5 md:col-span-1">
        <Meter done={queue.submitted} total={queue.total} />
        <p className="flex justify-between font-mono text-[11px] text-ink-soft tabular-nums">
          <span>
            {queue.submitted}/{queue.total} tasks submitted
          </span>
          <span data-testid="my-progress">
            you {mine} done · {left} left
          </span>
        </p>
      </div>
      <nav
        aria-label={`${queueTitle(queue)} screens`}
        className="col-start-2 row-start-1 flex items-center gap-1.5 md:col-start-3"
      >
        <Link
          to={`${base}/review`}
          className="rounded-[3px] border border-ink bg-ink px-3 py-1.5 text-xs font-medium text-paper"
        >
          {left > 0 ? 'Review' : 'Open'}
        </Link>
        <Link
          to={`${base}/adjudication`}
          className="rounded-[3px] border border-rule px-3 py-1.5 text-xs font-medium hover:border-ink-soft"
        >
          Adjudicate
        </Link>
        <Link
          to={`${base}/calibration`}
          className="rounded-[3px] border border-rule px-3 py-1.5 text-xs font-medium hover:border-ink-soft"
        >
          Calibration
        </Link>
      </nav>
    </li>
  )
}

export function QueueListPage() {
  const navigate = useNavigate()
  const queues = useQueues()
  const items = queues.data?.items ?? []
  const [selected, setSelected] = useState(0)
  const current = items[selected]

  function open(screen: 'review' | 'adjudication' | 'calibration') {
    if (current) void navigate(`/queues/${current.queue_id}/${screen}`)
  }

  const bindings: Binding[] = [
    {
      id: 'next',
      caps: ['J'],
      label: 'Next queue',
      match: plainKey('j', 'ArrowDown'),
      run: () => {
        setSelected((i) => Math.min(i + 1, items.length - 1))
      },
    },
    {
      id: 'prev',
      caps: ['K'],
      label: 'Previous queue',
      match: plainKey('k', 'ArrowUp'),
      run: () => {
        setSelected((i) => Math.max(i - 1, 0))
      },
    },
    {
      id: 'review',
      caps: ['Enter'],
      label: 'Review',
      match: plainKey('Enter', 'r'),
      run: () => {
        open('review')
      },
      disabled: !current,
    },
    {
      id: 'adjudicate',
      caps: ['D'],
      label: 'Adjudicate',
      match: letter('d'),
      run: () => {
        open('adjudication')
      },
      disabled: !current,
    },
    {
      id: 'calibration',
      caps: ['C'],
      label: 'Calibration',
      match: letter('c'),
      run: () => {
        open('calibration')
      },
      disabled: !current,
    },
    {
      id: 'gold',
      caps: ['G'],
      label: 'Gold sets',
      match: letter('g'),
      run: () => {
        void navigate('/gold')
      },
    },
  ]
  useKeymap(bindings)

  return (
    <>
      <main className="mx-auto w-full max-w-[1400px] flex-1 px-6 py-10">
        <div className="flex items-end justify-between gap-6">
          <div>
            <p className="font-mono text-xs tracking-[0.2em] text-faint uppercase">
              Queues
            </p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight">
              Review queues in this workspace
            </h1>
          </div>
          {queues.isSuccess && (
            <p className="font-mono text-xs text-faint">
              {items.length} {items.length === 1 ? 'queue' : 'queues'}
            </p>
          )}
        </div>

        {queues.isPending && (
          <p className="mt-10 text-sm text-faint">Loading queues…</p>
        )}
        {queues.isError && (
          <p role="alert" className="mt-10 text-sm text-signal">
            Could not load queues: {errorMessage(queues.error)}
          </p>
        )}
        {queues.isSuccess && items.length === 0 && (
          <div className="mt-10 max-w-lg rounded-[3px] border border-dashed border-rule p-6 text-sm text-ink-soft">
            <p className="font-medium text-ink">No queues yet.</p>
            <p className="mt-1">
              A workflow's human review step opens one. Run{' '}
              <code className="font-mono">molabel workflow run</code> on a
              workflow with a review step.
            </p>
          </div>
        )}
        {items.length > 0 && (
          <ul className="mt-8 divide-y divide-rule border-y border-rule">
            {items.map((queue, index) => (
              <QueueRow
                key={queue.queue_id}
                queue={queue}
                selected={index === selected}
                onSelect={() => {
                  setSelected(index)
                }}
              />
            ))}
          </ul>
        )}
      </main>
      <KeyLegend bindings={bindings} />
    </>
  )
}
