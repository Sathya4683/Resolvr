import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, ClipboardCheck, Link2, MessageSquareQuote, ThumbsUp } from 'lucide-react'
import { Link } from 'react-router'
import { Badge, Card, CardHeader, EmptyState, Mono, PageHeader, Skeleton, Stat } from '../components/ui'
import { api } from '../lib/api'
import { dateTime, pct, titleCase } from '../lib/format'
import type { AnalystReview } from '../lib/types'

interface QualitySummary {
  verdicts: Record<string, number>
  reviews: number
  citations_ok_rate: number | null
  agreement: Record<string, number | null>
  feedback: Record<string, number>
  review_status: Record<string, number>
  by_category: { category: string; reviews: number; correct: number }[]
}

const VERDICT_TONE = { correct: 'ok', partially_correct: 'warn', incorrect: 'danger' } as const

export default function Quality() {
  const summary = useQuery({ queryKey: ['quality'], queryFn: () => api.get<QualitySummary>('/v1/quality/summary') })
  const reviews = useQuery({ queryKey: ['quality', 'reviews'], queryFn: () => api.get<AnalystReview[]>('/v1/reviews?limit=50') })

  if (summary.isLoading || !summary.data) return <Skeleton className="mx-auto mt-16 h-96 max-w-6xl" />
  const s = summary.data
  const up = s.feedback.up ?? 0
  const down = s.feedback.down ?? 0
  const decided = (s.review_status.approved ?? 0) + (s.review_status.edited ?? 0) + (s.review_status.rejected ?? 0)

  return (
    <div className="mx-auto max-w-6xl px-6 pt-16 pb-16">
      <PageHeader title="Quality" subtitle="How good the assistant's answers are, measured by analysts, agents and admins." />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Answers marked correct"
          value={pct(s.reviews ? (s.verdicts.correct ?? 0) / s.reviews : null)}
          hint={`${s.verdicts.correct ?? 0} of ${s.reviews} analyst reviews`}
          icon={<CheckCircle2 className="size-3.5" />}
          tone="ok"
        />
        <Stat
          label="Citations proper"
          value={pct(s.citations_ok_rate)}
          hint="Cited source supports the step"
          icon={<Link2 className="size-3.5" />}
          tone="accent"
        />
        <Stat
          label="Agent thumbs up"
          value={pct(up + down ? up / (up + down) : null)}
          hint={`${up} up · ${down} down`}
          icon={<ThumbsUp className="size-3.5" />}
        />
        <Stat
          label="Admin edit / decline rate"
          value={pct(decided ? ((s.review_status.edited ?? 0) + (s.review_status.rejected ?? 0)) / decided : null)}
          hint={`${decided} critical drafts decided`}
          icon={<ClipboardCheck className="size-3.5" />}
          tone="warn"
        />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader title="Label agreement" subtitle="Share of AI labels analysts did not correct" />
          <div className="space-y-3 p-5">
            {Object.entries(s.agreement).map(([field, value]) => (
              <div key={field}>
                <div className="mb-1 flex justify-between text-sm">
                  <span className="text-ink-2">{titleCase(field)}</span>
                  <span className="text-ink tabular-nums">{pct(value)}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-raised">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${(value ?? 0) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Card>
        <Card>
          <CardHeader title="Accuracy by category" subtitle="Analyst verdict 'correct' per category" />
          {s.by_category.length ? (
            <table className="w-full text-sm">
              <tbody className="divide-y divide-line">
                {s.by_category.map((c) => (
                  <tr key={c.category}>
                    <td className="px-5 py-2.5 text-ink-2">{c.category}</td>
                    <td className="px-5 py-2.5 text-right text-ink-3 tabular-nums">
                      {c.correct}/{c.reviews}
                    </td>
                    <td className="w-20 px-5 py-2.5 text-right tabular-nums">{pct(c.correct / c.reviews)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="px-5 py-8 text-center text-sm text-ink-3">No reviews yet</p>
          )}
        </Card>
      </div>

      <Card className="mt-5">
        <CardHeader title="Recent analyst reviews" icon={<MessageSquareQuote className="size-4" />} />
        {!reviews.data?.length ? (
          <EmptyState icon={<ClipboardCheck className="size-5" />} title="No reviews yet" text="Analysts review answers from the review queue." />
        ) : (
          <div className="divide-y divide-line">
            {reviews.data.map((r) => (
              <div key={r.id} className="px-5 py-3.5">
                <div className="flex flex-wrap items-center gap-2 text-xs text-ink-3">
                  <Link to={`/tickets/${r.ticket_ref}`} className="font-mono text-accent hover:underline">
                    {r.ticket_ref}
                  </Link>
                  <Badge tone={VERDICT_TONE[r.verdict]}>{titleCase(r.verdict)}</Badge>
                  {!r.citations_ok && <Badge tone="danger">citations off</Badge>}
                  {Object.entries(r.corrected_labels).map(([k, v]) => (
                    <Badge key={k} tone="warn">
                      {k}: {r.original_labels[k] ?? '-'} → {v}
                    </Badge>
                  ))}
                  <span className="ml-auto">
                    {r.analyst} · {dateTime(r.created_at)}
                  </span>
                </div>
                {r.notes && <p className="mt-1.5 text-sm text-ink-2">{r.notes}</p>}
                <div className="mt-1 flex gap-3 text-[11px] text-ink-3">
                  {Object.entries(r.rubric).map(([k, v]) => (
                    <span key={k} className={v ? '' : 'text-danger'}>
                      {v ? '✓' : '✗'} {k}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
      <p className="mt-3 text-xs text-ink-3">
        Download the evaluation report as a PDF from <Link to="/reports" className="text-accent hover:underline">Reports</Link>.{' '}
        <Mono>Agreement</Mono> = labels the analyst kept as-is.
      </p>
    </div>
  )
}
