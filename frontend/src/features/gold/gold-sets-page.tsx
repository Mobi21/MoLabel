import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import type {
  GoldConflict,
  GoldItem,
  GoldSetSummary,
} from '@/api/generated/types.gen'
import { errorMessage } from '@/api/client'
import { goldSetQuery, goldSetsQuery } from '@/api/queries'
import { KeyLegend } from '@/components/key-legend'
import { ReadFailed } from '@/components/read-failed'
import { formatValue } from '@/features/review/rubric'
import { plural } from './promote-to-gold'
import { letter, plainKey, useKeymap, type Binding } from '@/lib/keymap'
import { cn } from '@/lib/utils'

function labels(expected: Record<string, unknown>) {
  return Object.entries(expected)
    .map(([field, value]) => `${field} ${formatValue(value)}`)
    .join(' · ')
}

function itemName(item: GoldItem) {
  return item.input_ref.external_id ?? item.item_id.slice(0, 8)
}

const SOURCE_TEXT: Record<GoldItem['provenance']['source'], string> = {
  adjudication: 'adjudicated',
  reviewer_agreement: 'reviewers agreed',
  single_reviewer: 'one reviewer',
}

function Additions({ items }: { items: GoldItem[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-faint">No items yet.</p>
  }
  return (
    <table className="w-full border-collapse border-y border-rule text-sm">
      <thead>
        <tr className="border-b border-rule text-left font-mono text-xs text-faint">
          <th className="py-2 pr-4 font-normal">record</th>
          <th className="py-2 pr-4 font-normal">expected</th>
          <th className="py-2 pr-4 font-normal">from</th>
          <th className="py-2 pr-4 font-normal">AI shown</th>
          <th className="py-2 font-normal">promoted</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr
            key={item.item_id}
            data-testid="gold-item"
            className="border-b border-rule last:border-b-0"
          >
            <th
              scope="row"
              className="py-2 pr-4 text-left font-mono font-medium"
            >
              {itemName(item)}
            </th>
            <td className="py-2 pr-4">{labels(item.expected)}</td>
            <td className="py-2 pr-4 text-ink-soft">
              {SOURCE_TEXT[item.provenance.source]}
              {item.provenance.model_failure && ' · model failure'}
            </td>
            <td className="py-2 pr-4 text-ink-soft">
              {item.provenance.ai_revealed
                ? item.provenance.accepted_ai_proposal
                  ? 'yes, accepted'
                  : 'yes'
                : 'no'}
            </td>
            <td className="py-2 font-mono text-xs text-ink-soft">
              {new Date(item.provenance.promoted_at).toLocaleString()}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Conflicts({ conflicts }: { conflicts: GoldConflict[] }) {
  if (conflicts.length === 0) {
    return <p className="text-sm text-faint">No conflicts.</p>
  }
  return (
    <ul className="space-y-2 text-sm">
      {conflicts.map((conflict, index) => (
        <li
          key={`${conflict.item_id}-${String(index)}`}
          data-testid="gold-conflict"
          className="rounded-[3px] border border-signal/40 bg-signal-soft/60 px-3 py-2"
        >
          <span className="font-mono">{itemName(conflict.gold)}</span> has two
          labels for one input: {labels(conflict.gold.expected)}, and{' '}
          {labels(conflict.other.expected)}. Both stay until a person edits the
          file.
        </li>
      ))}
    </ul>
  )
}

function GoldSet({ goldSetId }: { goldSetId: string }) {
  const detail = useQuery(goldSetQuery(goldSetId))
  if (detail.isError) {
    return (
      <ReadFailed
        error={detail.error}
        onRetry={() => {
          void detail.refetch()
        }}
      />
    )
  }
  if (!detail.isSuccess) {
    return <p className="text-sm text-faint">Reading the gold set…</p>
  }
  const set = detail.data
  return (
    <section aria-labelledby="gold-set-heading" className="min-w-0 space-y-6">
      <div>
        <h2 id="gold-set-heading" className="text-xl font-semibold">
          {set.name}
        </h2>
        <p className="mt-1 font-mono text-xs text-ink-soft tabular-nums">
          <span data-testid="gold-version">version {set.version}</span> ·{' '}
          <span data-testid="gold-item-count">
            {plural(set.item_count, 'item', 'items')}
          </span>{' '}
          · {set.task_schema} · {set.path}
        </p>
        <p className="mt-1 font-mono text-[11px] text-faint">
          {set.content_hash}
        </p>
        {!set.content_hash_matches && (
          <p role="status" className="mt-2 text-sm text-signal">
            gold.jsonl is not the file version {set.version} describes. It was
            edited outside MoLabel, or a write stopped partway. The next
            promotion or dedupe records the current file as the previous
            version.
          </p>
        )}
      </div>
      <section aria-label="Recent additions" className="space-y-3">
        <h3 className="text-base font-semibold">Recent additions</h3>
        <Additions items={set.recent_additions} />
      </section>
      <section aria-label="Conflicts" className="space-y-3">
        <h3 className="text-base font-semibold">Conflicts</h3>
        <Conflicts conflicts={set.conflicts} />
        {set.duplicates.length > 0 && (
          <p className="text-sm text-ink-soft">
            {set.duplicates.length} exact repeats;{' '}
            <code className="font-mono text-xs">
              molabel gold dedupe {set.gold_set_id}
            </code>{' '}
            removes them.
          </p>
        )}
      </section>
      <p className="text-sm text-ink-soft">
        Taken from {set.sources.length}{' '}
        {set.sources.length === 1 ? 'queue' : 'queues'}. Commit{' '}
        <code className="font-mono text-xs">
          {set.path.replace(/gold\.yaml$/, '')}
        </code>{' '}
        to keep this version in git.
      </p>
    </section>
  )
}

export function GoldSetsPage() {
  const { goldSetId } = useParams()
  const navigate = useNavigate()
  const list = useQuery(goldSetsQuery())
  const sets = list.data?.items ?? []
  const current = sets.find((s) => s.gold_set_id === goldSetId) ?? sets[0]
  const index = current ? sets.indexOf(current) : -1

  const go = (set: GoldSetSummary | undefined) => {
    if (set) void navigate(`/gold/${set.gold_set_id}`)
  }

  const bindings: Binding[] = [
    {
      id: 'next',
      caps: ['J'],
      label: 'Next gold set',
      match: letter('j'),
      run: () => {
        go(sets[index + 1])
      },
      disabled: index >= sets.length - 1,
    },
    {
      id: 'previous',
      caps: ['K'],
      label: 'Previous gold set',
      match: letter('k'),
      run: () => {
        go(sets[index - 1])
      },
      disabled: index <= 0,
    },
    {
      id: 'queues',
      caps: ['Esc'],
      label: 'Queues',
      match: plainKey('Escape'),
      run: () => {
        void navigate('/')
      },
    },
  ]
  useKeymap(bindings)

  return (
    <>
      <main className="mx-auto w-full max-w-[1400px] flex-1 px-6 py-8">
        <p className="font-mono text-xs tracking-[0.2em] text-faint uppercase">
          Gold sets
        </p>
        {list.isPending && (
          <p className="mt-6 text-sm text-faint">Loading gold sets…</p>
        )}
        {list.isError && (
          <p role="alert" className="mt-6 text-sm text-signal">
            {errorMessage(list.error)}
          </p>
        )}
        {list.isSuccess && sets.length === 0 && (
          <div className="mt-6 max-w-lg rounded-[3px] border border-dashed border-rule p-6 text-sm text-ink-soft">
            <p className="font-medium text-ink">No gold sets yet.</p>
            <p className="mt-1">
              Create one with{' '}
              <code className="font-mono">
                molabel gold create &lt;slug&gt; --task-schema &lt;slug&gt;
              </code>
              , then promote reviewed records from the adjudication or
              calibration screen.
            </p>
          </div>
        )}
        {current && (
          <div className="mt-6 grid gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
            <nav aria-label="Gold sets" className="min-w-0">
              <ul className="divide-y divide-rule border-y border-rule">
                {sets.map((set) => (
                  <li key={set.gold_set_id}>
                    <button
                      type="button"
                      data-testid="gold-set-row"
                      aria-current={set === current ? 'true' : undefined}
                      onClick={() => {
                        go(set)
                      }}
                      className={cn(
                        'flex w-full flex-col gap-0.5 border-l-2 px-3 py-2 text-left',
                        set === current
                          ? 'border-signal bg-sheet'
                          : 'border-transparent hover:bg-sheet',
                      )}
                    >
                      <span className="text-sm font-medium">{set.name}</span>
                      <span className="font-mono text-[11px] text-ink-soft">
                        v{set.version} ·{' '}
                        {plural(set.item_count, 'item', 'items')}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </nav>
            <GoldSet
              key={current.gold_set_id}
              goldSetId={current.gold_set_id}
            />
          </div>
        )}
      </main>
      <KeyLegend bindings={bindings} />
    </>
  )
}
