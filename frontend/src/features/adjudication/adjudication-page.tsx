import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { resolveQueueDisagreementMutation } from '@/api/generated/@tanstack/react-query.gen'
import type {
  DisagreementDetail,
  DisagreementSummary,
} from '@/api/generated/types.gen'
import { errorMessage } from '@/api/client'
import {
  disagreementQuery,
  disagreementsQuery,
  taskSchemaQuery,
} from '@/api/queries'
import { Kbd, KeyLegend } from '@/components/key-legend'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { QueueHeader } from '@/features/queues/queue-header'
import { useQueue } from '@/features/queues/queues'
import { RecordView } from '@/features/review/record-view'
import {
  formatValue,
  missingRequired,
  pickValue,
  rubricFields,
  type Labels,
  type RubricField,
} from '@/features/review/rubric'
import { RubricForm } from '@/features/review/rubric-form'
import {
  MOD,
  digitKey,
  letter,
  modEnter,
  plainKey,
  useKeymap,
  type Binding,
} from '@/lib/keymap'
import { cn } from '@/lib/utils'
import { agreedLabels, sourcesOf, take, type Source } from './resolution'

export function AdjudicationPage() {
  const { queueId = '' } = useParams()
  const queue = useQueue(queueId)
  const [params, setParams] = useSearchParams()
  const list = useQuery(disagreementsQuery(queueId))
  const items = list.data?.items ?? []
  const requested = params.get('record')
  const current =
    items.find((d) => d.record_id === requested) ??
    items.find((d) => d.status === 'pending') ??
    items[0]
  const index = current ? items.indexOf(current) : -1

  const go = (item: DisagreementSummary | undefined) => {
    if (item) setParams({ record: item.record_id })
  }

  // Pin the shown record, so a refetched list never swaps it out.
  const shown = current?.record_id
  useEffect(() => {
    if (requested === null && shown !== undefined) {
      setParams({ record: shown }, { replace: true })
    }
  }, [requested, shown, setParams])

  const nextPending =
    items.slice(index + 1).find((d) => d.status === 'pending') ??
    items.find((d) => d.status === 'pending' && d !== current)

  return (
    <>
      <QueueHeader queueId={queueId} queue={queue} />
      {list.isPending && (
        <p className="p-8 text-sm text-faint">Loading disagreements…</p>
      )}
      {list.isError && (
        <p role="alert" className="p-8 text-sm text-signal">
          {errorMessage(list.error)}
        </p>
      )}
      {list.isSuccess && items.length === 0 && (
        <EmptyState
          title="No disagreements in this queue."
          body="Disagreements appear once two reviewers label the same record differently."
        />
      )}
      {current && (
        <main className="mx-auto grid w-full max-w-[1400px] flex-1 gap-6 px-6 py-6 lg:grid-cols-[260px_minmax(0,1fr)]">
          <nav aria-label="Disagreements" className="min-w-0">
            <p className="mb-2 font-mono text-xs text-faint">
              {list.data?.unresolved ?? 0} of {items.length} unresolved
            </p>
            <ul className="divide-y divide-rule border-y border-rule">
              {items.map((item) => (
                <li key={item.record_id}>
                  <button
                    type="button"
                    data-testid="disagreement-row"
                    aria-current={item === current ? 'true' : undefined}
                    onClick={() => {
                      go(item)
                    }}
                    className={cn(
                      'flex w-full flex-col gap-0.5 border-l-2 px-3 py-2 text-left',
                      item === current
                        ? 'border-signal bg-sheet'
                        : 'border-transparent hover:bg-sheet',
                    )}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="font-mono text-sm">
                        {item.record_external_id ?? item.record_id.slice(0, 8)}
                      </span>
                      <span
                        className={cn(
                          'font-mono text-[11px]',
                          item.status === 'resolved'
                            ? 'text-go'
                            : 'text-signal',
                        )}
                      >
                        {item.status}
                      </span>
                    </span>
                    <span className="truncate text-xs text-ink-soft">
                      {item.fields_in_conflict.join(', ')} · {item.severity}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </nav>
          <Disagreement
            key={current.record_id}
            queueId={queueId}
            recordId={current.record_id}
            onNext={() => {
              go(items[index + 1])
            }}
            onResolved={() => {
              go(nextPending)
            }}
            onPrevious={() => {
              go(items[index - 1])
            }}
            hasNext={index < items.length - 1}
            hasPrevious={index > 0}
          />
        </main>
      )}
    </>
  )
}

function EmptyState({ title, body }: { title: string; body: string }) {
  const navigate = useNavigate()
  const bindings: Binding[] = [
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
      <main className="mx-auto w-full max-w-[1400px] flex-1 px-6 py-16">
        <h2 className="text-xl font-semibold">{title}</h2>
        <p className="mt-2 max-w-lg text-sm text-ink-soft">{body}</p>
      </main>
      <KeyLegend bindings={bindings} />
    </>
  )
}

interface DisagreementProps {
  queueId: string
  recordId: string
  onResolved: () => void
  onNext: () => void
  onPrevious: () => void
  hasNext: boolean
  hasPrevious: boolean
}

function Disagreement(props: DisagreementProps) {
  const detail = useQuery(disagreementQuery(props.queueId, props.recordId))
  const schema = useQuery({
    ...taskSchemaQuery(detail.data?.task_schema_id ?? ''),
    enabled: detail.data !== undefined,
  })
  const fields = useMemo(
    () => rubricFields(schema.data?.label_fields ?? []),
    [schema.data],
  )
  if (detail.isError) {
    return (
      <p role="alert" className="text-sm text-signal">
        {errorMessage(detail.error)}
      </p>
    )
  }
  if (!detail.isSuccess || !schema.isSuccess) {
    return <p className="text-sm text-faint">Loading the disagreement…</p>
  }
  return <Resolver {...props} detail={detail.data} fields={fields} />
}

function Resolver({
  queueId,
  detail,
  fields,
  onResolved,
  onNext,
  onPrevious,
  hasNext,
  hasPrevious,
}: DisagreementProps & {
  detail: DisagreementDetail
  fields: readonly RubricField[]
}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const sources = sourcesOf(detail)
  const conflicts = new Set(detail.fields_in_conflict)
  const resolved = detail.resolution ?? null
  const [labels, setLabels] = useState<Labels>(() =>
    agreedLabels(fields, detail),
  )
  const [active, setActive] = useState(() =>
    Math.max(
      0,
      fields.findIndex((f) => conflicts.has(f.name)),
    ),
  )
  const [rationale, setRationale] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const note = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    heading.current?.focus()
  }, [])

  const resolve = useMutation({
    ...resolveQueueDisagreementMutation(),
    onSuccess: (updated) => {
      queryClient.setQueryData(
        disagreementQuery(queueId, detail.record_id).queryKey,
        updated,
      )
      void queryClient.invalidateQueries({
        queryKey: disagreementsQuery(queueId).queryKey,
      })
      onResolved()
    },
    onError: (error) => {
      setProblem(errorMessage(error))
    },
  })

  const pending = fields
    .filter((f) => conflicts.has(f.name))
    .filter((f) => labels[f.name] === undefined)
    .map((f) => f.name)
  const missing = [...new Set([...pending, ...missingRequired(fields, labels)])]

  function nextConflict(from: number) {
    const after = fields.findIndex((f, i) => i > from && conflicts.has(f.name))
    return after === -1 ? from : after
  }

  function pick(source: Source | undefined, whole: boolean) {
    if (source === undefined || resolved) return
    const field = fields[active]
    setLabels((current) =>
      take(fields, current, source, whole ? null : (field?.name ?? null)),
    )
    setProblem(null)
    if (!whole) setActive((i) => nextConflict(i))
  }

  function submit() {
    if (resolved || resolve.isPending) return
    if (missing.length > 0) {
      setProblem(`Settle ${missing.join(', ')} first.`)
      setActive(fields.findIndex((f) => f.name === missing[0]))
      return
    }
    resolve.mutate({
      path: { queue_id: queueId, record_id: detail.record_id },
      body: {
        resolution: 'resolve',
        resolved_labels: labels,
        rationale: rationale.trim() === '' ? null : rationale.trim(),
      },
    })
  }

  const field = fields[active]
  const byLetter = new Map<string, Source>(
    sources.flatMap((source) =>
      source.letter === null ? [] : [[source.letter, source] as const],
    ),
  )
  const bindings: Binding[] = [
    {
      id: 'take',
      caps: [...byLetter.keys()].map((l) => l.toUpperCase()),
      label: 'Take that column for this field (Shift: every field)',
      match: (event) =>
        !event.ctrlKey &&
        !event.metaKey &&
        !event.altKey &&
        byLetter.has(event.key.toLowerCase()),
      run: (event) => {
        pick(byLetter.get(event.key.toLowerCase()), event.shiftKey)
      },
      disabled: resolved !== null,
    },
    {
      id: 'write',
      caps: ['1–9'],
      label: 'Write a value',
      match: digitKey,
      run: (event) => {
        if (field === undefined || resolved) return
        const next = pickValue(field, labels, Number(event.key))
        if (next) setLabels(next)
      },
      disabled: resolved !== null,
    },
    {
      id: 'field-next',
      caps: ['↓'],
      label: 'Next field',
      match: plainKey('ArrowDown'),
      run: () => {
        setActive((i) => Math.min(i + 1, fields.length - 1))
      },
    },
    {
      id: 'field-previous',
      caps: ['↑'],
      label: 'Previous field',
      match: plainKey('ArrowUp'),
      run: () => {
        setActive((i) => Math.max(i - 1, 0))
      },
    },
    {
      id: 'resolve',
      caps: [MOD, 'Enter'],
      label: 'Resolve and next',
      match: modEnter,
      run: submit,
      inText: true,
      disabled: resolved !== null || resolve.isPending,
    },
    {
      id: 'next',
      caps: ['J'],
      label: 'Next disagreement',
      match: letter('j'),
      run: onNext,
      disabled: !hasNext,
    },
    {
      id: 'previous',
      caps: ['K'],
      label: 'Previous disagreement',
      match: letter('k'),
      run: onPrevious,
      disabled: !hasPrevious,
    },
    {
      id: 'note',
      caps: ['N'],
      label: 'Note',
      match: letter('n'),
      run: () => {
        note.current?.focus()
      },
      disabled: resolved !== null,
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
      <section
        aria-labelledby="disagreement-heading"
        className="animate-settle min-w-0 space-y-6"
      >
        <div className="flex flex-wrap items-baseline gap-3">
          <h2
            id="disagreement-heading"
            ref={heading}
            tabIndex={-1}
            className="font-mono text-sm font-medium outline-none"
          >
            {detail.record_external_id ?? detail.record_id.slice(0, 8)}
          </h2>
          <span className="font-mono text-xs text-faint">
            {detail.reviewer_count} reviewers disagree on{' '}
            {detail.fields_in_conflict.join(', ')} · {detail.severity} severity
          </span>
        </div>
        <RecordView item={detail} />

        <table
          data-testid="side-by-side"
          className="w-full border-collapse border-y border-rule text-sm"
        >
          <thead>
            <tr className="border-b border-rule text-left">
              <th className="py-2 pr-4 font-mono text-xs font-normal text-faint">
                field
              </th>
              {sources.map((source) => (
                <th
                  key={`${source.kind}-${source.name}-${String(source.letter)}`}
                  scope="col"
                  className="py-2 pr-4 font-medium"
                >
                  <span className="flex items-center gap-2">
                    {source.letter && <Kbd>{source.letter.toUpperCase()}</Kbd>}
                    {source.name}
                    {source.decision && (
                      <span className="font-mono text-[11px] font-normal text-faint">
                        {source.decision}
                      </span>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {fields.map((f) => (
              <tr
                key={f.name}
                className={cn(
                  'border-b border-rule last:border-b-0',
                  conflicts.has(f.name) && 'bg-signal-soft/60',
                )}
              >
                <th
                  scope="row"
                  className="py-2 pr-4 text-left font-mono text-xs font-normal"
                >
                  {f.name}
                  {conflicts.has(f.name) && (
                    <span className="ml-2 text-signal">conflict</span>
                  )}
                </th>
                {sources.map((source) => (
                  <td
                    key={`${source.kind}-${source.name}-${String(source.letter)}`}
                    className="py-2 pr-4"
                  >
                    {formatValue(source.labels[f.name])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>

        {resolved ? (
          <div
            data-testid="resolution"
            className="rounded-[3px] border border-go/40 bg-go-soft p-4"
          >
            <p className="font-mono text-xs text-go">
              resolved by {resolved.adjudicator_name ?? 'an adjudicator'} ·{' '}
              {new Date(resolved.resolved_at).toLocaleString()}
            </p>
            <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
              {fields.map((f) => (
                <div key={f.name} className="contents">
                  <dt className="font-mono text-xs leading-6 text-ink-soft">
                    {f.name}
                  </dt>
                  <dd className="leading-6">
                    {formatValue(resolved.resolved_labels?.[f.name])}
                  </dd>
                </div>
              ))}
            </dl>
            {resolved.rationale && (
              <p className="mt-2 text-sm text-ink-soft">{resolved.rationale}</p>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <h3 className="font-mono text-xs text-faint">
              Resolution · take a column or write a value
            </h3>
            <RubricForm
              fields={fields}
              labels={labels}
              onChange={setLabels}
              active={active}
              onActivate={setActive}
              marked={conflicts}
            />
            <label className="block">
              <span className="font-mono text-xs text-faint">
                Rationale (optional)
              </span>
              <Textarea
                ref={note}
                value={rationale}
                onChange={(event) => {
                  setRationale(event.target.value)
                }}
                placeholder="Why this resolution"
                className="mt-1"
              />
            </label>
            <div className="flex items-center gap-3">
              <Button
                onClick={submit}
                disabled={resolve.isPending}
                className="ml-auto"
              >
                Resolve
              </Button>
            </div>
            {problem && (
              <p role="alert" className="text-sm text-signal">
                {problem}
              </p>
            )}
          </div>
        )}
      </section>
      <KeyLegend bindings={bindings} />
    </>
  )
}
