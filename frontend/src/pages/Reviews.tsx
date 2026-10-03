import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { CheckCheck, ClipboardCheck, Lock, Send, Undo2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { SentimentBadge, SeverityBadge, SeverityIcon } from '../components/badges'
import { CitationChip, SourceCard, SourceDrawer } from '../components/sources'
import { Badge, Button, Card, CardHeader, EmptyState, Mono, PageHeader, Skeleton } from '../components/ui'
import { api, ApiError } from '../lib/api'
import { dateTime, pct, timeAgo, titleCase } from '../lib/format'
import type { Category, QueueItem, Source, TicketDetail } from '../lib/types'

const VERDICTS = [
  { value: 'correct', label: 'Correct', tone: 'border-ok/50 bg-ok/10 text-ok' },
  { value: 'partially_correct', label: 'Partly correct', tone: 'border-warn/50 bg-warn/10 text-warn' },
  { value: 'incorrect', label: 'Incorrect', tone: 'border-danger/50 bg-danger/10 text-danger' },
] as const

const RUBRIC = [
  { key: 'correct', label: 'Correct', hint: 'Fixes the actual problem' },
  { key: 'safe', label: 'Safe', hint: 'No risky or unauthorised promises' },
  { key: 'actionable', label: 'Actionable', hint: 'An agent can follow the steps' },
  { key: 'complete', label: 'Complete', hint: 'Nothing important missing' },
] as const

export default function Reviews() {
  const [params, setParams] = useSearchParams()
  const selected = Number(params.get('a')) || null
  const queue = useQuery({
    queryKey: ['reviews', 'queue'],
    queryFn: () => api.get<QueueItem[]>('/v1/reviews/queue'),
    refetchInterval: 15_000,
  })

  return (
    <div className="mx-auto max-w-7xl px-6 pt-16 pb-16">
      <PageHeader
        title="Review queue"
        subtitle="A sample of AI answers to check. Items most likely to have problems come first. Only one analyst can review an item at a time."
      />
      {queue.isLoading ? (
        <Skeleton className="h-96" />
      ) : !queue.data?.length ? (
        <Card>
          <EmptyState icon={<CheckCheck className="size-5" />} title="Queue is empty" text="Every analysed ticket has been reviewed." />
        </Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[340px_1fr]">
          <div className="space-y-2">
            {queue.data.map((item) => (
              <button
                key={item.analysis_id}
                disabled={item.locked}
                onClick={() => setParams({ a: String(item.analysis_id) })}
                className={clsx(
                  'w-full rounded-xl border p-3.5 text-left transition disabled:cursor-not-allowed',
                  selected === item.analysis_id
                    ? 'border-accent/50 bg-accent/[0.06]'
                    : item.locked
                      ? 'border-line bg-card opacity-60'
                      : 'border-line bg-card hover:border-line-strong',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <SeverityIcon severity={item.severity} />
                    <Mono className="text-ink-2">{item.ticket_ref}</Mono>
                  </span>
                  <span className="text-[11px] text-ink-3">{timeAgo(item.created_at)}</span>
                </div>
                <div className="mt-2 line-clamp-2 text-sm text-ink-2">{item.subject || item.snippet}</div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {item.reasons.map((r) => (
                    <Badge key={r} tone={r === 'thumbs down' || r === 'abstained' ? 'warn' : 'neutral'}>
                      {r}
                    </Badge>
                  ))}
                </div>
                {item.locked && (
                  <div className="mt-2 flex items-center gap-1.5 text-xs text-ink-3">
                    <Lock className="size-3" /> {item.claimed_by} is reviewing this
                  </div>
                )}
              </button>
            ))}
          </div>
          {selected ? (
            <ReviewForm key={selected} analysisId={selected} onDone={() => setParams({})} />
          ) : (
            <Card>
              <EmptyState icon={<ClipboardCheck className="size-5" />} title="Pick an item to review" text="Opening an item locks it to you for 15 minutes." />
            </Card>
          )}
        </div>
      )}
    </div>
  )
}

function ReviewForm({ analysisId, onDone }: { analysisId: number; onDone: () => void }) {
  const qc = useQueryClient()
  const [ticket, setTicket] = useState<TicketDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [verdict, setVerdict] = useState<string>('')
  const [citationsOk, setCitationsOk] = useState(true)
  const [rubric, setRubric] = useState({ correct: true, safe: true, actionable: true, complete: true })
  const [corrections, setCorrections] = useState<Record<string, string>>({})
  const [notes, setNotes] = useState('')
  const [openSource, setOpenSource] = useState<Source | null>(null)
  const categories = useQuery({ queryKey: ['categories'], queryFn: () => api.get<Category[]>('/v1/categories') })

  //claim the item when it opens, keep the lock alive while the form is open, release it when leaving
  useEffect(() => {
    let alive = true
    const claim = () =>
      api
        .post<TicketDetail>(`/v1/reviews/${analysisId}/claim`)
        .then((t) => alive && setTicket(t))
        .catch((e: ApiError) => alive && setError(e.message))
    claim()
    const keepAlive = setInterval(claim, 5 * 60_000)
    return () => {
      alive = false
      clearInterval(keepAlive)
      api.post(`/v1/reviews/${analysisId}/release`).catch(() => {})
    }
  }, [analysisId])

  const submit = useMutation({
    mutationFn: () =>
      api.post(`/v1/reviews/${analysisId}`, {
        verdict,
        citations_ok: citationsOk,
        rubric,
        corrections,
        notes: notes.trim() || undefined,
      }),
    onSuccess: () => {
      toast.success('Review saved. Your note will guide answers for similar complaints.')
      qc.invalidateQueries({ queryKey: ['reviews'] })
      qc.invalidateQueries({ queryKey: ['quality'] })
      onDone()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  if (error)
    return (
      <Card>
        <EmptyState icon={<Lock className="size-5" />} title="Can't open this item" text={error} />
      </Card>
    )
  if (!ticket?.analysis) return <Skeleton className="h-[600px]" />
  const a = ticket.analysis
  const steps = a.steps.length ? a.steps : (a.draft.steps ?? [])

  const labelRow = (field: string, label: string, current: React.ReactNode, options: { value: string; label: string }[]) => (
    <div className="grid grid-cols-[84px_minmax(0,1fr)_170px] items-center gap-3 px-5 py-2.5 text-sm">
      <span className="text-ink-3">{label}</span>
      <span>{current}</span>
      <select
        className={clsx('input h-8 py-0 text-xs', corrections[field] && 'border-warn/50 text-warn')}
        value={corrections[field] ?? ''}
        onChange={(e) => {
          const next = { ...corrections }
          if (e.target.value) next[field] = e.target.value
          else delete next[field]
          setCorrections(next)
        }}
      >
        <option value="">Looks right</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            Should be: {o.label}
          </option>
        ))}
      </select>
    </div>
  )

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              <Mono className="text-ink-2">{ticket.ref}</Mono> {ticket.subject || 'Complaint'}
            </span>
          }
          subtitle={`Analysed ${dateTime(a.created_at)} · ${titleCase(a.outcome)} · confidence ${pct(a.parsed.confidence)}`}
          action={
            <Button size="sm" variant="ghost" icon={<Undo2 className="size-3.5" />} onClick={onDone}>
              Release
            </Button>
          }
        />
        <p className="px-5 py-4 text-[15px] leading-relaxed whitespace-pre-wrap">{ticket.complaint}</p>
      </Card>

      <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
        <div className="min-w-0 space-y-5">
          <Card>
            <CardHeader title="Labels" subtitle="Correct anything the assistant got wrong" />
            <div className="divide-y divide-line">
              {labelRow('category', 'Category', ticket.category?.name ?? 'Unclear', (categories.data ?? []).map((c) => ({ value: c.slug, label: c.name })))}
              {labelRow('product', 'Product', titleCase(ticket.product) || '-', ['broadband', 'mobile', 'dth', 'billing'].map((p) => ({ value: p, label: titleCase(p) })))}
              {labelRow('severity', 'Severity', <SeverityBadge severity={ticket.severity} />, ['low', 'medium', 'high', 'critical'].map((p) => ({ value: p, label: titleCase(p) })))}
              {labelRow('sentiment', 'Sentiment', <SentimentBadge sentiment={ticket.sentiment} />, ['angry', 'frustrated', 'neutral', 'positive'].map((p) => ({ value: p, label: titleCase(p) })))}
            </div>
          </Card>

          <Card>
            <CardHeader title="Drafted resolution" subtitle={a.outcome === 'abstained' ? a.abstain_reason ?? undefined : 'Check each step against its cited source'} />
            {steps.length ? (
              <ol className="space-y-1 p-3">
                {steps.map((s, i) => (
                  <li key={i} className="flex gap-3 rounded-lg px-2 py-2">
                    <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-raised text-xs font-semibold text-ink-2">{i + 1}</span>
                    <div>
                      <p className="text-sm leading-relaxed">{s.text}</p>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {s.citations.map((c) => (
                          <CitationChip key={c} refId={c} onClick={() => setOpenSource(a.retrieved.find((x) => x.ref === c) ?? null)} />
                        ))}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="px-5 py-4 text-sm text-ink-3">No steps were drafted for this one.</p>
            )}
          </Card>

          <Card>
            <CardHeader title="Retrieved sources" />
            <div className="grid gap-2.5 p-4 2xl:grid-cols-2">
              {a.retrieved.map((s) => (
                <SourceCard key={s.ref} source={s} onOpen={() => setOpenSource(s)} cited={steps.some((st) => st.citations.includes(s.ref))} />
              ))}
            </div>
          </Card>
        </div>

        <Card className="h-fit p-5 xl:sticky xl:top-16">
          <div className="text-sm font-semibold">Your verdict</div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            {VERDICTS.map((v) => (
              <button
                key={v.value}
                onClick={() => setVerdict(v.value)}
                className={clsx(
                  'rounded-lg border px-2 py-2 text-xs font-medium transition',
                  verdict === v.value ? v.tone : 'border-line text-ink-2 hover:border-line-strong',
                )}
              >
                {v.label}
              </button>
            ))}
          </div>

          <div className="mt-5 text-sm font-semibold">Rubric</div>
          <div className="mt-2 space-y-1.5">
            {RUBRIC.map((r) => (
              <label key={r.key} className="flex cursor-pointer items-start gap-3 rounded-lg px-2 py-1.5 hover:bg-raised/50">
                <input
                  type="checkbox"
                  className="mt-0.5 accent-[#6366f1]"
                  checked={rubric[r.key]}
                  onChange={(e) => setRubric({ ...rubric, [r.key]: e.target.checked })}
                />
                <span>
                  <span className="text-sm">{r.label}</span>
                  <span className="block text-xs text-ink-3">{r.hint}</span>
                </span>
              </label>
            ))}
            <label className="flex cursor-pointer items-start gap-3 rounded-lg px-2 py-1.5 hover:bg-raised/50">
              <input type="checkbox" className="mt-0.5 accent-[#6366f1]" checked={citationsOk} onChange={(e) => setCitationsOk(e.target.checked)} />
              <span>
                <span className="text-sm">Citations are proper</span>
                <span className="block text-xs text-ink-3">Each cited source actually supports its step</span>
              </span>
            </label>
          </div>

          <div className="mt-5">
            <label className="label">Note for future answers</label>
            <textarea
              rows={4}
              className="input"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Speed complaints without an outage should be medium, not high."
            />
            <p className="mt-1.5 text-[11px] leading-relaxed text-ink-3">
              Notes and label corrections are stored as guidance and used straight away when a similar complaint comes in.
            </p>
          </div>

          <Button
            variant="primary"
            className="mt-5 w-full"
            icon={<Send className="size-4" />}
            disabled={!verdict}
            loading={submit.isPending}
            onClick={() => submit.mutate()}
          >
            Submit review
          </Button>
          {Object.keys(corrections).length > 0 && (
            <p className="mt-2 text-center text-xs text-warn">{Object.keys(corrections).length} label correction(s)</p>
          )}
        </Card>
      </div>
      <SourceDrawer source={openSource} onClose={() => setOpenSource(null)} />
    </div>
  )
}
