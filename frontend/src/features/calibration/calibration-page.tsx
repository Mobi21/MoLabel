import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import type { AgreementScope } from '@/api/generated/types.gen'
import { errorMessage } from '@/api/client'
import { agreementQuery, taskSchemaQuery } from '@/api/queries'
import { KeyLegend } from '@/components/key-legend'
import {
  PromoteToGold,
  usePromoteToGold,
} from '@/features/gold/promote-to-gold'
import { QueueHeader } from '@/features/queues/queue-header'
import { useQueue } from '@/features/queues/queues'
import { useReviewer } from '@/features/session/session'
import { letter, plainKey, useKeymap, type Binding } from '@/lib/keymap'
import { cn } from '@/lib/utils'
import {
  RELIABLE,
  TENTATIVE,
  band,
  formatAlpha,
  formatShare,
  weakestField,
} from './alpha'

const BAND_TEXT = {
  reliable: 'text-go',
  tentative: 'text-ink',
  unreliable: 'text-signal',
} as const

/** Where alpha falls between 0 and 1, against Krippendorff's thresholds. */
function AlphaScale({ alpha }: { alpha: number | null | undefined }) {
  const at = (v: number) => `${String(Math.min(Math.max(v, 0), 1) * 100)}%`
  return (
    <div className="relative mt-3 h-8" aria-hidden>
      <div className="absolute inset-x-0 top-3 h-1.5 rounded-full bg-rule" />
      <div
        className="absolute top-3 right-0 h-1.5 rounded-r-full bg-go/30"
        style={{ left: at(RELIABLE) }}
      />
      {[TENTATIVE, RELIABLE].map((tick) => (
        <div
          key={tick}
          className="absolute top-1.5 h-4 w-px bg-ink-soft"
          style={{ left: at(tick) }}
        >
          <span className="absolute top-5 -translate-x-1/2 font-mono text-[10px] text-faint">
            {tick.toFixed(3).replace(/^0/, '')}
          </span>
        </div>
      ))}
      {alpha !== null && alpha !== undefined && (
        <div
          className="absolute top-0.5 size-5 -translate-x-1/2 rounded-full border-2 border-paper bg-ink shadow"
          style={{ left: at(alpha) }}
        />
      )}
    </div>
  )
}

function Headline({
  title,
  note,
  scope,
  testId,
}: {
  title: string
  note?: string
  scope: AgreementScope
  testId: string
}) {
  const weakest = weakestField(scope.fields)
  const pooled = scope.pooled
  return (
    <div
      role="group"
      aria-label={title}
      className="rounded-[3px] border border-rule bg-sheet p-5"
    >
      <p className="font-mono text-xs text-faint">{title}</p>
      {note && <p className="font-mono text-[11px] text-ink-soft">{note}</p>}
      {weakest ? (
        <>
          <p
            className={cn(
              'mt-1 font-mono text-4xl font-medium tracking-tight tabular-nums',
              BAND_TEXT[band(weakest.alpha)],
            )}
          >
            α {formatAlpha(weakest.alpha)}
          </p>
          <p className="mt-1 text-xs text-ink-soft">
            {band(weakest.alpha)} · weakest measured field,{' '}
            <span className="font-mono text-ink">{weakest.field}</span>, which a
            min_agreement gate checks
          </p>
        </>
      ) : (
        <p className="mt-1 text-sm text-faint">
          No field was measured. {pooled.null_reasons?.krippendorff_alpha ?? ''}
        </p>
      )}
      <AlphaScale alpha={weakest?.alpha} />
      <p className="mt-3 font-mono text-[11px] text-ink-soft tabular-nums">
        pooled over every field{' '}
        <span data-testid={testId} className="text-ink">
          α {formatAlpha(pooled.krippendorff_alpha)}
        </span>{' '}
        · {formatShare(pooled.percent_agreement)} of {pooled.comparisons ?? 0}{' '}
        value pairs agree
      </p>
    </div>
  )
}

function AlphaCell({ alpha }: { alpha: number | null | undefined }) {
  return (
    <td
      className={cn(
        'py-2 pr-4',
        alpha !== null && alpha !== undefined && BAND_TEXT[band(alpha)],
      )}
    >
      {formatAlpha(alpha)}
    </td>
  )
}

function FieldTable({
  inter,
  humanAgent,
}: {
  inter: AgreementScope
  humanAgent: AgreementScope
}) {
  const names = [
    ...new Set([
      ...Object.keys(inter.fields ?? {}),
      ...Object.keys(humanAgent.fields ?? {}),
    ]),
  ]
  return (
    <table className="w-full border-collapse border-y border-rule text-sm">
      <thead>
        <tr className="border-b border-rule text-left font-mono text-xs text-faint">
          <th className="py-2 pr-4 font-normal">field</th>
          <th className="py-2 pr-4 font-normal">reviewers α</th>
          <th className="py-2 pr-4 font-normal">agree</th>
          <th className="py-2 pr-4 font-normal">Cohen κ</th>
          <th className="py-2 pr-4 font-normal">pairs</th>
          <th className="py-2 pr-4 font-normal">reviewers vs AI α</th>
          <th className="py-2 font-normal">agree with AI</th>
        </tr>
      </thead>
      <tbody className="font-mono tabular-nums">
        {names.map((name) => {
          const a = inter.fields?.[name]
          const h = humanAgent.fields?.[name]
          return (
            <tr
              key={name}
              data-testid={`agreement-${name}`}
              className="border-b border-rule last:border-b-0"
            >
              <th scope="row" className="py-2 pr-4 text-left font-medium">
                {name}
              </th>
              <AlphaCell alpha={a?.krippendorff_alpha} />
              <td className="py-2 pr-4">{formatShare(a?.percent_agreement)}</td>
              <td className="py-2 pr-4">{formatAlpha(a?.cohen_kappa)}</td>
              <td className="py-2 pr-4">{a?.comparisons ?? 0}</td>
              <AlphaCell alpha={h?.krippendorff_alpha} />
              <td className="py-2">{formatShare(h?.percent_agreement)}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function SkippedFields({
  scope,
  title,
}: {
  scope: AgreementScope
  title: string
}) {
  const skipped = Object.entries(scope.skipped_fields ?? {})
  if (skipped.length === 0) return null
  return (
    <div>
      <h3 className="font-mono text-xs text-faint">{title}</h3>
      <ul className="mt-2 space-y-1.5 text-sm">
        {skipped.map(([name, reason]) => (
          <li key={name} data-testid="skipped-field" className="flex gap-3">
            <span className="w-28 shrink-0 font-mono">{name}</span>
            <span className="text-ink-soft">{reason ?? 'Not measured.'}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function CalibrationPage() {
  const { queueId = '' } = useParams()
  const queue = useQueue(queueId)
  const reviewer = useReviewer()
  const navigate = useNavigate()
  const report = useQuery(agreementQuery(reviewer.workspace_id, queueId))
  const schema = useQuery({
    ...taskSchemaQuery(queue?.task_schema_id ?? ''),
    enabled: queue !== undefined,
  })
  const promotion = usePromoteToGold({
    queueId,
    taskSchemaSlug: schema.data?.task_schema_slug,
  })
  const promotes = queue !== undefined && queue.kind !== 'calibrate'

  const bindings: Binding[] = [
    {
      id: 'review',
      caps: ['R'],
      label: 'Review',
      match: letter('r'),
      run: () => {
        void navigate(`/queues/${queueId}/review`)
      },
    },
    {
      id: 'adjudicate',
      caps: ['D'],
      label: 'Adjudicate',
      match: letter('d'),
      run: () => {
        void navigate(`/queues/${queueId}/adjudication`)
      },
    },
    {
      ...promotion.binding,
      disabled: promotion.binding.disabled === true || !promotes,
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

  const data = report.data
  return (
    <>
      <QueueHeader queueId={queueId} queue={queue} />
      <main className="mx-auto w-full max-w-[1400px] flex-1 space-y-8 px-6 py-8">
        {report.isPending && (
          <p className="text-sm text-faint">Measuring agreement…</p>
        )}
        {report.isError && (
          <p role="alert" className="text-sm text-signal">
            {errorMessage(report.error)}
          </p>
        )}
        {data && (
          <>
            <p className="font-mono text-xs text-ink-soft">
              {data.reviewer_count ?? 0} reviewers · {data.record_count ?? 0}{' '}
              records rated · Krippendorff's alpha, nominal
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              <Headline
                title="Reviewers against each other"
                scope={data.inter_annotator}
                testId="alpha-pooled"
              />
              <Headline
                title="Reviewers against the AI proposal"
                note="includes accepts of shown proposals"
                scope={data.human_agent}
                testId="alpha-human-agent"
              />
            </div>
            <section aria-label="Per field" className="space-y-3">
              <h2 className="text-base font-semibold">Per field</h2>
              <FieldTable
                inter={data.inter_annotator}
                humanAgent={data.human_agent}
              />
            </section>
            <section
              aria-label="Skipped fields"
              className="grid gap-6 md:grid-cols-2"
            >
              <SkippedFields
                scope={data.inter_annotator}
                title="Skipped between reviewers"
              />
              <SkippedFields
                scope={data.human_agent}
                title="Skipped against the AI"
              />
            </section>
            {promotes && (
              <PromoteToGold
                promotion={promotion}
                what="agreed and adjudicated records"
              />
            )}
            {(data.warnings ?? []).length > 0 && (
              <ul className="space-y-1 text-sm text-ink-soft">
                {(data.warnings ?? []).map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            )}
          </>
        )}
      </main>
      <KeyLegend bindings={bindings} />
    </>
  )
}
