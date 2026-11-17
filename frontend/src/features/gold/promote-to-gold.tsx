import { useId, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { promoteToGoldSetMutation } from '@/api/generated/@tanstack/react-query.gen'
import type { GoldWriteReport, Skipped } from '@/api/generated/types.gen'
import { errorMessage } from '@/api/client'
import { goldSetsQuery, invalidateGoldSets } from '@/api/queries'
import { Kbd } from '@/components/key-legend'
import { Button } from '@/components/ui/button'
import { formatValue } from '@/features/review/rubric'
import { letter, type Binding } from '@/lib/keymap'

interface Target {
  queueId: string
  /** The queue's task schema; only a gold set of that schema can take it. */
  taskSchemaSlug: string | undefined
  /** Only these records of the queue; every eligible one when unset. */
  recordIds?: string[]
}

/**
 * Promote a queue's reviewed records into a gold set of its task schema.
 * The screen puts `binding` in its keymap, so G promotes and the legend
 * shows it.
 */
export function usePromoteToGold({
  queueId,
  taskSchemaSlug,
  recordIds,
}: Target) {
  const queryClient = useQueryClient()
  const sets = useQuery(goldSetsQuery())
  const matching = (sets.data?.items ?? []).filter(
    (set) => set.task_schema === taskSchemaSlug,
  )
  const [chosen, setChosen] = useState<string | null>(null)
  const selected =
    matching.find((set) => set.gold_set_id === chosen) ?? matching[0]
  const promote = useMutation({
    ...promoteToGoldSetMutation(),
    onSuccess: () => {
      invalidateGoldSets(queryClient)
    },
  })

  function run() {
    if (!selected || promote.isPending) return
    promote.mutate({
      path: { gold_set_id: selected.gold_set_id },
      body: { queue_id: queueId, record_ids: recordIds ?? null },
    })
  }

  const binding: Binding = {
    id: 'promote',
    caps: ['G'],
    label: 'Promote to gold',
    match: letter('g'),
    run,
    disabled: !selected || promote.isPending,
  }
  return {
    sets,
    matching,
    selected,
    choose: setChosen,
    promote,
    run,
    binding,
    taskSchemaSlug,
  }
}

export type Promotion = ReturnType<typeof usePromoteToGold>

export function plural(n: number, one: string, many: string) {
  return `${String(n)} ${n === 1 ? one : many}`
}

function recordName(skipped: Pick<Skipped, 'external_id' | 'record_id'>) {
  return skipped.external_id ?? skipped.record_id?.slice(0, 8) ?? 'a record'
}

function PromotionResult({ report }: { report: GoldWriteReport }) {
  const set = report.gold_set
  const { added, duplicates } = report.counts
  const reasons = new Map<string, Skipped[]>()
  for (const skipped of report.skipped) {
    reasons.set(skipped.message, [
      ...(reasons.get(skipped.message) ?? []),
      skipped,
    ])
  }
  return (
    <div data-testid="promote-result" className="space-y-2 text-sm">
      <p className="font-medium">
        {report.written
          ? `Added ${plural(added, 'item', 'items')} to ${set.name}, now version ${String(set.version)} with ${plural(set.item_count, 'item', 'items')}.`
          : `Nothing added to ${set.name}; it stays at version ${String(set.version)}.`}
      </p>
      {duplicates > 0 && (
        <p className="text-ink-soft">
          {plural(duplicates, 'record is', 'records are')} already in the set
          with the same labels.
        </p>
      )}
      {report.conflicts.map((conflict) => (
        <p
          key={conflict.item_id}
          data-testid="promote-conflict"
          className="text-signal"
        >
          {recordName({
            external_id: conflict.other.input_ref.external_id ?? null,
            record_id: conflict.other.input_ref.record_id ?? null,
          })}{' '}
          conflicts with gold on {conflict.fields.join(', ')}:{' '}
          {conflict.fields
            .map(
              (field) =>
                `gold has ${formatValue(conflict.gold.expected[field])}, this has ${formatValue(conflict.other.expected[field])}`,
            )
            .join('; ')}
          . Gold is kept; edit {set.path.replace(/gold\.yaml$/, 'gold.jsonl')}{' '}
          to change it.
        </p>
      ))}
      {[...reasons].map(([message, skipped]) => (
        <p key={message} className="text-ink-soft">
          Skipped {skipped.map(recordName).join(', ')}: {message}
        </p>
      ))}
    </div>
  )
}

/** The gold-set picker, the promote button, and what the last promotion did. */
export function PromoteToGold({
  promotion,
  what,
}: {
  promotion: Promotion
  /** What a promotion takes, such as "this record". */
  what: string
}) {
  const pickerId = useId()
  const { sets, matching, selected, promote, taskSchemaSlug } = promotion
  return (
    <section
      aria-label="Promote to gold"
      className="space-y-3 rounded-[3px] border border-rule bg-sheet p-4"
    >
      <h3 className="font-mono text-xs text-faint">Promote to gold</h3>
      {sets.isError && (
        <p role="alert" className="text-sm text-signal">
          {errorMessage(sets.error)}
        </p>
      )}
      {sets.isSuccess && matching.length === 0 && (
        <p className="text-sm text-ink-soft">
          No gold set holds {taskSchemaSlug ?? 'this task schema'} yet. Create
          one with{' '}
          <code className="font-mono text-xs">
            molabel gold create &lt;slug&gt; --task-schema{' '}
            {taskSchemaSlug ?? '<task-schema>'}
          </code>
          .
        </p>
      )}
      {selected && (
        <div className="flex flex-wrap items-center gap-3">
          <label htmlFor={pickerId} className="text-sm text-ink-soft">
            Gold set
          </label>
          <select
            id={pickerId}
            value={selected.gold_set_id}
            onChange={(event) => {
              promotion.choose(event.target.value)
            }}
            className="h-9 rounded-[3px] border border-rule bg-paper px-2 text-sm"
          >
            {matching.map((set) => (
              <option key={set.gold_set_id} value={set.gold_set_id}>
                {set.name} · v{set.version} ·{' '}
                {plural(set.item_count, 'item', 'items')}
              </option>
            ))}
          </select>
          <Button
            variant="outline"
            onClick={promotion.run}
            disabled={promote.isPending}
          >
            <Kbd>G</Kbd> Promote {what}
          </Button>
        </div>
      )}
      <div role="status" aria-live="polite">
        {promote.isSuccess && <PromotionResult report={promote.data} />}
        {promote.isError && (
          <p className="text-sm text-signal">{errorMessage(promote.error)}</p>
        )}
      </div>
    </section>
  )
}
