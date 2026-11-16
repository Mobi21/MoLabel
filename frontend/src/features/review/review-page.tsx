import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import {
  revealAiEndpointMutation,
  skipTaskEndpointMutation,
  submitCorrectionEndpointMutation,
  submitReviewEndpointMutation,
} from '@/api/generated/@tanstack/react-query.gen'
import type { ReviewItemResponse } from '@/api/generated/types.gen'
import { errorMessage } from '@/api/client'
import { taskSchemaQuery } from '@/api/queries'
import { KeyLegend } from '@/components/key-legend'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { QueueHeader } from '@/features/queues/queue-header'
import { useQueue } from '@/features/queues/queues'
import {
  MOD,
  digitKey,
  isTextTarget,
  letter,
  modEnter,
  plainKey,
  useKeymap,
  type Binding,
} from '@/lib/keymap'
import { cn } from '@/lib/utils'
import { RecordView } from './record-view'
import {
  changedFields,
  formatValue,
  missingRequired,
  parseLabels,
  pickKey,
  rubricFields,
  submission,
  type Labels,
  type RubricField,
} from './rubric'
import { RubricForm } from './rubric-form'
import {
  reviewTaskKey,
  useReviewSession,
  type ReviewSession,
} from './review-session'

export function ReviewPage() {
  const { queueId = '' } = useParams()
  const queue = useQueue(queueId)
  const session = useReviewSession(queueId)
  const navigate = useNavigate()
  const item = session.item.data
  const schema = useQuery({
    ...taskSchemaQuery(item?.task_schema_id ?? ''),
    enabled: item !== undefined,
  })
  const fields = useMemo(
    () => rubricFields(schema.data?.label_fields ?? []),
    [schema.data],
  )

  let body: React.ReactNode
  if (session.trail.isError || session.claim.isError) {
    body = (
      <p role="alert" className="p-8 text-sm text-signal">
        {errorMessage(session.trail.error ?? session.claim.error)}
      </p>
    )
  } else if (session.currentId === null && session.head.kind === 'empty') {
    body = (
      <QueueDone
        session={session}
        onOpen={(screen) => {
          void navigate(`/queues/${queueId}/${screen}`)
        }}
      />
    )
  } else if (item === undefined || !schema.isSuccess) {
    body = <p className="p-8 text-sm text-faint">Loading the next item…</p>
  } else {
    body = (
      <ReviewItem
        key={item.id}
        item={item}
        fields={fields}
        instructions={schema.data.instructions ?? null}
        session={session}
        total={
          session.position.total +
          Math.max(
            0,
            (queue?.my_remaining ?? 0) - (session.head.kind === 'task' ? 1 : 0),
          )
        }
      />
    )
  }

  return (
    <>
      <QueueHeader queueId={queueId} queue={queue} />
      {body}
    </>
  )
}

function QueueDone({
  session,
  onOpen,
}: {
  session: ReviewSession
  onOpen: (screen: 'adjudication' | 'calibration') => void
}) {
  const navigate = useNavigate()
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus()
  }, [])
  const bindings: Binding[] = [
    {
      id: 'previous',
      caps: ['K'],
      label: 'Previous item',
      match: letter('k'),
      run: () => {
        session.go(session.previousId)
      },
      disabled: session.previousId === null,
    },
    {
      id: 'adjudicate',
      caps: ['D'],
      label: 'Adjudicate',
      match: letter('d'),
      run: () => {
        onOpen('adjudication')
      },
    },
    {
      id: 'calibration',
      caps: ['C'],
      label: 'Calibration',
      match: letter('c'),
      run: () => {
        onOpen('calibration')
      },
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
      <main className="mx-auto w-full max-w-[1400px] flex-1 px-6 py-16">
        <h2
          ref={heading}
          tabIndex={-1}
          data-testid="queue-done"
          className="text-2xl font-semibold tracking-tight outline-none"
        >
          Nothing left for you in this queue.
        </h2>
        <p className="mt-2 max-w-lg text-sm text-ink-soft">
          You reviewed {session.position.total}{' '}
          {session.position.total === 1 ? 'item' : 'items'}. Step back with K to
          correct one, or see how your labels compare in calibration.
        </p>
        <div className="mt-6 flex gap-2">
          <Button
            onClick={() => {
              onOpen('calibration')
            }}
          >
            Open calibration
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              onOpen('adjudication')
            }}
          >
            Open adjudication
          </Button>
        </div>
      </main>
      <KeyLegend bindings={bindings} />
    </>
  )
}

const DECISION_STYLES = {
  accept: 'border-go/40 bg-go-soft text-go',
  edit: 'border-signal/40 bg-signal-soft text-signal',
  reject: 'border-signal/40 bg-signal-soft text-signal',
  none: 'border-rule bg-sheet text-ink-soft',
} as const

function ReviewItem({
  item,
  fields,
  instructions,
  session,
  total,
}: {
  item: ReviewItemResponse
  fields: readonly RubricField[]
  instructions: string | null
  session: ReviewSession
  /** Items in the reviewer's share of the queue, done or not. */
  total: number
}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const proposal = item.agent_output?.labels ?? null
  const previous = item.review ? parseLabels(fields, item.review.labels) : null
  const [form, setForm] = useState<Labels>(
    () => previous ?? parseLabels(fields, proposal),
  )
  const [touched, setTouched] = useState(false)
  const [active, setActive] = useState(0)
  const [rationale, setRationale] = useState(item.review?.rationale ?? '')
  const [problem, setProblem] = useState<string | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const note = useRef<HTMLTextAreaElement>(null)
  const texts = useRef(new Map<string, HTMLTextAreaElement>())

  const isHead = session.isHead
  const isSkipped = item.status === 'skipped'
  const blind = item.blind_review_policy === 'hide_agent_outputs_by_default'
  const canReveal =
    isHead && blind && !item.ai_revealed && item.agent_output == null

  useEffect(() => {
    heading.current?.focus()
  }, [])

  const proposalId = item.agent_output?.id
  useEffect(() => {
    if (proposal !== null && !touched && previous === null) {
      setForm(parseLabels(fields, proposal))
    }
    // A revealed proposal fills an untouched form; nothing else refills it.
  }, [proposalId])

  function change(labels: Labels) {
    setForm(labels)
    setTouched(true)
    setProblem(null)
  }

  const onDone = {
    onError: (error: unknown) => {
      setProblem(errorMessage(error))
    },
  }
  const submit = useMutation({
    ...submitReviewEndpointMutation(),
    onSuccess: (response) => {
      void queryClient.invalidateQueries({ queryKey: reviewTaskKey(item.id) })
      session.advanceHead(response.next_task)
    },
    ...onDone,
  })
  const skip = useMutation({
    ...skipTaskEndpointMutation(),
    onSuccess: (response) => {
      void queryClient.invalidateQueries({ queryKey: reviewTaskKey(item.id) })
      session.advanceHead(response.next_task)
    },
    ...onDone,
  })
  const reveal = useMutation({
    ...revealAiEndpointMutation(),
    onSuccess: (response) => {
      queryClient.setQueryData(reviewTaskKey(item.id), {
        ...response.task,
        review: null,
      })
    },
    ...onDone,
  })
  const correct = useMutation({
    ...submitCorrectionEndpointMutation(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: reviewTaskKey(item.id) })
      session.refreshTrail()
      session.goNext()
    },
    ...onDone,
  })
  const busy =
    submit.isPending || skip.isPending || reveal.isPending || correct.isPending

  const outcome = submission(fields, form, proposal)
  const missing = missingRequired(fields, form)
  const corrections = previous ? changedFields(fields, previous, form) : []

  function save(decision: 'reject' | null = null) {
    if (busy || isSkipped) return
    const rationaleText = rationale.trim() === '' ? null : rationale.trim()
    if (decision === null && missing.length > 0) {
      setActive(fields.findIndex((f) => f.name === missing[0]))
      setProblem(`Pick a value for ${missing.join(', ')} first.`)
      return
    }
    const body =
      decision === 'reject'
        ? { decision, labels: form }
        : { decision: outcome.decision, labels: outcome.labels }
    if (!isHead) {
      if (corrections.length === 0 && decision === null) {
        session.goNext()
        return
      }
      correct.mutate({
        path: { task_id: item.id },
        body: { ...body, rationale: rationaleText },
      })
      return
    }
    submit.mutate({
      path: { task_id: item.id },
      body: { ...body, rationale: rationaleText, auto_claim_next: true },
    })
  }

  const field = fields[active]
  const bindings: Binding[] = [
    {
      id: 'pick',
      caps: ['1–9'],
      label: 'Pick a value',
      match: digitKey,
      run: (event) => {
        if (field === undefined || isSkipped) return
        const next = pickKey(field, form, Number(event.key))
        if (next === null) return
        change(next)
        if (field.kind === 'choice' || field.kind === 'bool') {
          setActive((i) => Math.min(i + 1, fields.length - 1))
        }
      },
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
      id: 'write',
      caps: ['Enter'],
      label: 'Write in a text field',
      match: plainKey('Enter'),
      run: () => {
        if (field?.kind === 'text') texts.current.get(field.name)?.focus()
      },
      disabled: field?.kind !== 'text',
    },
    {
      id: 'leave-text',
      caps: ['Esc'],
      label: 'Leave text',
      match: (event) => event.key === 'Escape' && isTextTarget(event.target),
      run: () => {
        heading.current?.focus()
      },
      inText: true,
    },
    {
      id: 'submit',
      caps: [MOD, 'Enter'],
      label: isHead ? 'Submit and next' : 'Save and next',
      match: modEnter,
      run: () => {
        save()
      },
      inText: true,
      disabled: busy || isSkipped,
    },
    {
      id: 'next',
      caps: ['J'],
      label: 'Next item',
      match: letter('j'),
      run: session.goNext,
      disabled: !session.hasNext,
    },
    {
      id: 'previous',
      caps: ['K'],
      label: 'Previous item',
      match: letter('k'),
      run: () => {
        session.go(session.previousId)
      },
      disabled: session.previousId === null,
    },
    {
      id: 'skip',
      caps: ['S'],
      label: 'Skip',
      match: letter('s'),
      run: () => {
        if (!busy) skip.mutate({ path: { task_id: item.id } })
      },
      disabled: !isHead || busy,
    },
    {
      id: 'reveal',
      caps: ['R'],
      label: 'Reveal AI',
      match: letter('r'),
      run: () => {
        if (!busy) reveal.mutate({ path: { task_id: item.id } })
      },
      disabled: !canReveal || busy,
    },
    {
      id: 'adopt',
      caps: ['A'],
      label: 'Use AI labels',
      match: letter('a'),
      run: () => {
        if (proposal !== null) change(parseLabels(fields, proposal))
      },
      disabled: proposal === null || isSkipped,
    },
    {
      id: 'reject',
      caps: ['X'],
      label: 'Reject',
      match: letter('x'),
      run: () => {
        save('reject')
      },
      disabled: busy || isSkipped,
    },
    {
      id: 'note',
      caps: ['N'],
      label: 'Note',
      match: letter('n'),
      run: () => {
        note.current?.focus()
      },
      disabled: isSkipped,
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

  const decisionKey = outcome.decision ?? 'none'
  const position = `${String(session.position.index + 1)} of ${String(total)}`

  return (
    <>
      <main className="mx-auto grid w-full max-w-[1400px] flex-1 gap-8 px-6 py-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(360px,1fr)]">
        <section
          aria-labelledby="item-heading"
          className="animate-settle min-w-0"
        >
          <div className="flex items-baseline gap-3">
            <h2
              id="item-heading"
              ref={heading}
              tabIndex={-1}
              className="font-mono text-sm font-medium outline-none"
            >
              {item.record_external_id ?? item.record_id.slice(0, 8)}
            </h2>
            <span
              aria-live="polite"
              className="font-mono text-xs text-faint tabular-nums"
            >
              item {position}
            </span>
            {!isHead && (
              <span className="rounded-[3px] border border-rule px-1.5 py-px font-mono text-[11px] text-ink-soft">
                {isSkipped
                  ? 'you skipped this'
                  : `submitted · ${item.review?.decision ?? 'labels'}`}
              </span>
            )}
          </div>
          <RecordView item={item} />
          {instructions && (
            <details className="mt-6 text-sm text-ink-soft">
              <summary className="cursor-pointer font-mono text-xs text-faint">
                Instructions
              </summary>
              <p className="mt-2 whitespace-pre-line">{instructions}</p>
            </details>
          )}
        </section>

        <section aria-label="Labels" className="min-w-0 space-y-5">
          <ProposalPanel
            item={item}
            fields={fields}
            form={form}
            canReveal={canReveal}
            onReveal={() => {
              reveal.mutate({ path: { task_id: item.id } })
            }}
          />

          <div className="flex flex-wrap items-center gap-3">
            <span
              data-testid="decision-preview"
              className={cn(
                'rounded-[3px] border px-2 py-1 font-mono text-xs',
                DECISION_STYLES[decisionKey],
              )}
            >
              {outcome.decision === 'accept' && 'accept · keeps the proposal'}
              {outcome.decision === 'edit' &&
                `edit · ${outcome.changed.join(', ')}`}
              {outcome.decision === null && 'labels · no proposal shown'}
            </span>
            <div className="ml-auto flex gap-2">
              {isHead && (
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() => {
                    skip.mutate({ path: { task_id: item.id } })
                  }}
                >
                  Skip
                </Button>
              )}
              <Button
                variant="outline"
                disabled={busy || isSkipped}
                onClick={() => {
                  save('reject')
                }}
              >
                Reject
              </Button>
              <Button
                disabled={busy || isSkipped}
                onClick={() => {
                  save()
                }}
              >
                {isHead ? 'Submit and next' : 'Save correction'}
              </Button>
            </div>
          </div>
          {problem && (
            <p role="alert" className="text-sm text-signal">
              {problem}
            </p>
          )}
          <RubricForm
            fields={fields}
            labels={form}
            onChange={change}
            active={active}
            onActivate={setActive}
            marked={new Set(outcome.changed)}
            disabled={isSkipped}
            textRef={(name, element) => {
              if (element) texts.current.set(name, element)
              else texts.current.delete(name)
            }}
          />

          <label className="block">
            <span className="font-mono text-xs text-faint">
              Note (optional)
            </span>
            <Textarea
              ref={note}
              value={rationale}
              disabled={isSkipped}
              onChange={(event) => {
                setRationale(event.target.value)
              }}
              placeholder="Why you labelled it this way"
              className="mt-1"
            />
          </label>
        </section>
      </main>
      <KeyLegend bindings={bindings} />
    </>
  )
}

function ProposalPanel({
  item,
  fields,
  form,
  canReveal,
  onReveal,
}: {
  item: ReviewItemResponse
  fields: readonly RubricField[]
  form: Labels
  canReveal: boolean
  onReveal: () => void
}) {
  const output = item.agent_output
  if (output) {
    const proposed = parseLabels(fields, output.labels)
    const changed = new Set(changedFields(fields, proposed, form))
    return (
      <div
        data-testid="ai-proposal"
        className="rounded-[3px] border border-rule bg-sheet"
      >
        <div className="flex items-center justify-between border-b border-rule px-3 py-2">
          <span className="font-mono text-xs font-medium">AI proposal</span>
          {item.ai_revealed && (
            <span className="font-mono text-[11px] text-faint">
              revealed by you
            </span>
          )}
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 px-3 py-2 text-sm">
          {fields.map((f) => (
            <div key={f.name} className="contents">
              <dt className="font-mono text-xs leading-6 text-faint">
                {f.name}
              </dt>
              <dd
                className={cn(
                  'leading-6',
                  changed.has(f.name) && 'text-signal line-through',
                )}
              >
                {formatValue(output.labels[f.name])}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    )
  }
  if (canReveal) {
    return (
      <div
        data-testid="ai-proposal-hidden"
        className="flex items-center justify-between gap-3 rounded-[3px] border border-dashed border-rule px-3 py-2.5"
      >
        <span className="text-sm text-ink-soft">
          Blind queue. Label it yourself first; the AI proposal stays hidden
          until you reveal it.
        </span>
        <Button variant="outline" size="sm" onClick={onReveal}>
          Reveal AI
        </Button>
      </div>
    )
  }
  return (
    <p className="rounded-[3px] border border-dashed border-rule px-3 py-2.5 text-sm text-faint">
      {item.blind_review_policy === 'no_agent'
        ? 'This queue shows no AI proposal.'
        : 'No AI proposal was shown for this item.'}
    </p>
  )
}
