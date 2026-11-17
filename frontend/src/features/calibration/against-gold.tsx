import { useQuery } from '@tanstack/react-query'
import type { GoldFieldScore } from '@/api/generated/types.gen'
import { errorMessage } from '@/api/client'
import { calibrationReportQuery } from '@/api/queries'
import { formatAlpha, formatShare } from './alpha'

function Score({ score }: { score: GoldFieldScore | undefined }) {
  return (
    <>
      <td className="py-2 pr-4">{formatShare(score?.accuracy)}</td>
      <td
        className="py-2 pr-4"
        title={score?.null_reasons?.cohen_kappa ?? undefined}
      >
        {formatAlpha(score?.cohen_kappa)}
      </td>
    </>
  )
}

/** Each reviewer of a calibration queue against the gold set's labels. */
export function AgainstGold({ queueId }: { queueId: string }) {
  const report = useQuery(calibrationReportQuery(queueId))
  if (report.isPending) {
    return <p className="text-sm text-faint">Scoring reviewers against gold…</p>
  }
  if (report.isError) {
    return (
      <p role="alert" className="text-sm text-signal">
        {errorMessage(report.error)}
      </p>
    )
  }
  const data = report.data
  return (
    <section aria-label="Reviewers against gold" className="space-y-3">
      <h2 className="text-base font-semibold">Reviewers against gold</h2>
      <p className="font-mono text-xs text-ink-soft">
        {data.gold_set_id} v{data.gold_version} · {data.items} items · accuracy
        and Cohen's κ with gold as the second rater
      </p>
      {data.reviewers.length === 0 ? (
        <p className="text-sm text-faint">No reviewer has answered yet.</p>
      ) : (
        <table className="w-full border-collapse border-y border-rule text-sm">
          <thead>
            <tr className="border-b border-rule text-left font-mono text-xs text-faint">
              <th className="py-2 pr-4 font-normal">reviewer</th>
              <th className="py-2 pr-4 font-normal">answered</th>
              <th className="py-2 pr-4 font-normal">exact match</th>
              <th className="py-2 pr-4 font-normal">accuracy</th>
              <th className="py-2 pr-4 font-normal">κ</th>
              {data.fields.map((field) => (
                <th key={field} colSpan={2} className="py-2 pr-4 font-normal">
                  {field} accuracy · κ
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {data.reviewers.map((reviewer) => (
              <tr
                key={reviewer.reviewer_id}
                data-testid="reviewer-against-gold"
                className="border-b border-rule last:border-b-0"
              >
                <th
                  scope="row"
                  className="py-2 pr-4 text-left font-sans font-medium"
                >
                  {reviewer.reviewer_name}
                </th>
                <td className="py-2 pr-4">{reviewer.items_answered}</td>
                <td className="py-2 pr-4">
                  {formatShare(reviewer.exact_match)}
                </td>
                <Score score={reviewer.pooled} />
                {data.fields.map((field) => (
                  <Score key={field} score={reviewer.fields?.[field]} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {(data.warnings ?? []).map((warning) => (
        <p key={warning} className="text-sm text-signal">
          {warning}
        </p>
      ))}
    </section>
  )
}
