import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Check, CheckCheck, ClipboardCheck, Lock, Send, Undo2 } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { SentimentBadge, SeverityBadge, SeverityIcon } from '../components/badges'
import { CitationChip, SourceCard, SourceDrawer } from '../components/sources'
import { Button, Card, CardHeader, EmptyState, Mono, PageHeader, Skeleton } from '../components/ui'
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

const PRODUCTS = ['broadband', 'mobile', 'dth', 'billing']
const SEVERITIES = ['low', 'medium', 'high', 'critical']
const SENTIMENTS = ['angry', 'frustrated', 'neutral', 'positive']

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
        subtitle="A sample of AI answers to check, likely problems first. Opening an item locks it to you for 15 minutes."
        actions={
          <Link to="/categories" className="text-sm text-accent hover:underline">
            Spotted a new kind of issue? Add a category
          </Link>
        }
      />
      {queue.isLoading ? (
        <Skeleton className="h-96" />
      ) : !queue.data?.length ? (
        <Card>
          <EmptyState icon={<CheckCheck className="size-5" />} title="Queue is empty" text="Every analysed ticket has been reviewed." />
        </Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
          <div className="space-y-1.5 lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto lg:pr-1">
            <div className="px-1 pb-1 text-xs text-ink-3">{queue.data.length} to review</div>
            {queue.data.map((item) => (
              <QueueCard
                key={item.analysis_id}
                item={item}
                active={selected === item.analysis_id}
                onOpen={() => setParams({ a: String(item.analysis_id) })}
              />
            ))}
          </div>
          {selected ? (
            <ReviewForm key={selected} analysisId={selected} onDone={() => setParams({})} />
          ) : (
            <Card>
              <EmptyState
                icon={<ClipboardCheck className="size-5" />}
                title="Pick an item to review"
                text="Check the labels and the drafted steps, then leave a verdict and a note for future answers."
              />
            </Card>
          )}
        </div>
      )}
    </div>
  )
}

function QueueCard({ item, active, onOpen }: { item: QueueItem; active: boolean; onOpen: () => void }) {
  return (
    <button
      disabled={item.locked}
      onClick={onOpen}
      className={clsx(
        'w-full rounded-lg border px-3 py-2.5 text-left transition disabled:cursor-not-allowed',
        active
          ? 'border-accent/50 bg-accent/[0.06]'
          : item.locked
            ? 'border-line bg-card opacity-55'
            : 'border-line bg-card hover:border-line-strong',
      )}
    >
      <div className="flex items-center gap-2">
        <SeverityIcon severity={item.severity} />
        <Mono className="text-ink-2">{item.ticket_ref}</Mono>
        <span className="ml-auto text-[11px] text-ink-3">{timeAgo(item.created_at)}</span>
      </div>
      <div className="mt-1.5 line-clamp-2 text-[13px] leading-snug text-ink-2">{item.subject || item.snippet}</div>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        {item.reasons.map((r) => (
          <span
            key={r}
            className={clsx(
              'rounded px-1.5 py-0.5 text-[10.5px] font-medium',
              r === 'thumbs down' || r === 'abstained' ? 'bg-warn/10 text-warn' : 'bg-raised text-ink-3',
            )}
          >
            {r}
          </span>
        ))}
      </div>
      {item.locked && (
        <div className="mt-1.5 flex items-center gap-1 text-[11px] text-ink-3">
          <Lock className="size-3" /> {item.claimed_by} is reviewing
        </div>
      )}
    </button>
  )
}

function LabelField({
  label,
  current,
  value,
  options,
  onChange,
}: {
  label: string
  current: ReactNode
  value: string
  options: { value: string; label: string }[]
  onChange: (v: string) => void
}) {
  return (
    <div className={clsx('rounded-lg border p-3', value ? 'border-warn/40 bg-warn/[0.04]' : 'border-line bg-panel')}>
      <div className="text-[11px] font-semibold tracking-wide text-ink-3 uppercase">{label}</div>
      <div className="mt-1.5 min-h-6 text-sm text-ink">{current}</div>
      <select
        className={clsx('input mt-2 h-8 py-0 text-xs', value && 'border-warn/50 text-warn')}
        value={value}
        onChange={(e) => onChange(e.target.value)}
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
  const correct = (field: string) => (v: string) => {
    const next = { ...corrections }
    if (v) next[field] = v
    else delete next[field]
    setCorrections(next)
  }
  const options = (values: string[]) => values.map((v) => ({ value: v, label: titleCase(v) }))

  return (
    <div className="min-w-0 space-y-5">
      <Card>
        <CardHeader
          title={
            <span className="flex flex-wrap items-center gap-2">
              <Mono className="text-ink-2">{ticket.ref}</Mono>
              <span>{ticket.subject || 'Complaint'}</span>
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

      <Card>
        <CardHeader title="Labels" subtitle="Leave 'Looks right' or pick what it should have been" />
        <div className="grid gap-3 p-4 sm:grid-cols-2">
          <LabelField
            label="Category"
            current={ticket.category?.name ?? <span className="text-ink-3">Unclear</span>}
            value={corrections.category ?? ''}
            options={(categories.data ?? []).map((c) => ({ value: c.slug, label: c.name }))}
            onChange={correct('category')}
          />
          <LabelField
            label="Product"
            current={titleCase(ticket.product) || <span className="text-ink-3">-</span>}
            value={corrections.product ?? ''}
            options={options(PRODUCTS)}
            onChange={correct('product')}
          />
          <LabelField
            label="Severity"
            current={<SeverityBadge severity={ticket.severity} reason={ticket.critical_reason} />}
            value={corrections.severity ?? ''}
            options={options(SEVERITIES)}
            onChange={correct('severity')}
          />
          <LabelField
            label="Sentiment"
            current={<SentimentBadge sentiment={ticket.sentiment} />}
            value={corrections.sentiment ?? ''}
            options={options(SENTIMENTS)}
            onChange={correct('sentiment')}
          />
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Drafted resolution"
          subtitle={a.outcome === 'abstained' ? (a.abstain_reason ?? undefined) : 'Click a citation to check the source it came from'}
        />
        {steps.length ? (
          <ol className="space-y-1 p-3">
            {steps.map((s, i) => (
              <li key={i} className="flex gap-3 rounded-lg px-2 py-2">
                <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-raised text-xs font-semibold text-ink-2">
                  {i + 1}
                </span>
                <div className="min-w-0">
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
        {a.draft.customer_reply && (
          <div className="mx-4 mb-4 rounded-lg border border-line bg-panel p-3 text-sm text-ink-2">
            <span className="text-xs font-semibold tracking-wide text-ink-3 uppercase">Reply to customer · </span>
            {a.draft.customer_reply}
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="Retrieved sources" subtitle="What the assistant had to work with" />
        <div className="grid gap-2.5 p-4 xl:grid-cols-2">
          {a.retrieved.map((s) => (
            <SourceCard key={s.ref} source={s} onOpen={() => setOpenSource(s)} cited={steps.some((st) => st.citations.includes(s.ref))} />
          ))}
        </div>
      </Card>

      <Card>
        <CardHeader title="Your review" subtitle="Doesn't change the ticket, it measures quality and guides future answers" />
        <div className="grid gap-6 p-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
          <div>
            <div className="label">Verdict</div>
            <div className="grid grid-cols-3 gap-2">
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

            <div className="label mt-5">Rubric</div>
            <div className="grid gap-2 sm:grid-cols-2">
              {RUBRIC.map((r) => (
                <Toggle
                  key={r.key}
                  checked={rubric[r.key]}
                  onChange={(v) => setRubric({ ...rubric, [r.key]: v })}
                  label={r.label}
                  hint={r.hint}
                />
              ))}
              <Toggle
                checked={citationsOk}
                onChange={setCitationsOk}
                label="Citations proper"
                hint="Each source supports its step"
              />
            </div>
          </div>

          <div className="flex flex-col">
            <label className="label">Note for future answers</label>
            <textarea
              rows={5}
              className="input flex-1"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Customers back from abroad need network selection and APN reset, not an IR pack."
            />
            <p className="mt-1.5 text-[11px] leading-relaxed text-ink-3">
              Notes and label corrections are used straight away as guidance when a similar complaint comes in.
            </p>
            <div className="mt-4 flex items-center justify-between gap-3">
              <span className="text-xs text-warn">
                {Object.keys(corrections).length > 0 && `${Object.keys(corrections).length} label correction(s)`}
              </span>
              <Button
                variant="primary"
                icon={<Send className="size-4" />}
                disabled={!verdict}
                loading={submit.isPending}
                onClick={() => submit.mutate()}
              >
                Submit review
              </Button>
            </div>
          </div>
        </div>
      </Card>
      <SourceDrawer source={openSource} onClose={() => setOpenSource(null)} />
    </div>
  )
}

function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  hint: string
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={clsx(
        'flex items-start gap-2.5 rounded-lg border px-3 py-2 text-left transition',
        checked ? 'border-line bg-panel' : 'border-danger/40 bg-danger/[0.05]',
      )}
    >
      <span
        className={clsx(
          'mt-0.5 grid size-4 shrink-0 place-items-center rounded border',
          checked ? 'border-accent-strong bg-accent-strong text-white' : 'border-danger/60',
        )}
      >
        {checked && <Check className="size-3" />}
      </span>
      <span>
        <span className={clsx('block text-sm', checked ? 'text-ink' : 'text-danger')}>{label}</span>
        <span className="block text-[11px] text-ink-3">{hint}</span>
      </span>
    </button>
  )
}
