import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  ChevronDown,
  Clipboard,
  Cpu,
  FileSearch,
  Hourglass,
  ListChecks,
  MessageSquareText,
  MessagesSquare,
  Plus,
  RefreshCw,
  ShieldAlert,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  User as UserIcon,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { ReviewBadge, SentimentBadge, SeverityBadge, StatusBadge } from '../components/badges'
import { CitationChip, SourceCard, SourceDrawer } from '../components/sources'
import { Badge, Button, Card, CardHeader, EmptyState, Mono, Modal, Skeleton } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { dateTime, pct, titleCase } from '../lib/format'
import type { Analysis, Source, TicketDetail as Ticket } from '../lib/types'

export default function TicketDetail() {
  const { ref } = useParams()
  const { user } = useAuth()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [openSource, setOpenSource] = useState<Source | null>(null)
  const [resolving, setResolving] = useState(false)

  const { data: ticket, isLoading, error } = useQuery({
    queryKey: ['ticket', ref],
    queryFn: () => api.get<Ticket>(`/v1/tickets/${ref}`),
    //while an admin is reviewing, keep checking so the agent sees the decision quickly
    refetchInterval: (q) => (q.state.data?.status === 'pending_review' ? 10_000 : false),
  })

  const reanalyze = useMutation({
    mutationFn: () => api.post<Ticket>(`/v1/tickets/${ref}/reanalyze`),
    onSuccess: (t) => {
      qc.setQueryData(['ticket', ref], t)
      qc.invalidateQueries({ queryKey: ['tickets'] })
      toast.success('Analysis refreshed')
    },
    onError: (e: Error) => toast.error(e.message),
  })

  if (isLoading) return <TicketSkeleton />
  if (error || !ticket)
    return <EmptyState icon={<FileSearch className="size-5" />} title="Ticket not found" text={(error as Error)?.message} />

  const a = ticket.analysis
  const cited = new Set(a?.steps.flatMap((s) => s.citations) ?? [])
  const sourceByRef = new Map((a?.retrieved ?? []).map((s) => [s.ref, s]))

  return (
    <div className="mx-auto max-w-5xl px-6 pt-16 pb-24">
      {/* header */}
      <div className="mb-6">
        <div className="flex flex-wrap items-center gap-2 text-xs text-ink-3">
          <Mono className="rounded-md border border-line bg-raised px-1.5 py-0.5 text-ink-2">{ticket.ref}</Mono>
          <StatusBadge status={ticket.status} review={a?.review_status} />
          <span>·</span>
          <span>{dateTime(ticket.created_at)}</span>
          {ticket.created_by && (
            <>
              <span>·</span>
              <span className="flex items-center gap-1">
                <UserIcon className="size-3" />
                {ticket.created_by.full_name}
              </span>
            </>
          )}
          {ticket.channel && <Badge>{ticket.channel}</Badge>}
          {ticket.customer_ref && <Mono>{ticket.customer_ref}</Mono>}
          {ticket.city && <span>{ticket.city}</span>}
        </div>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight">{ticket.subject || 'Customer complaint'}</h1>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
        <div className="min-w-0 space-y-5">
          <Card>
            <CardHeader title="Complaint" icon={<MessageSquareText className="size-4" />} />
            <p className="px-5 py-4 text-[15px] leading-relaxed whitespace-pre-wrap text-ink">{ticket.complaint}</p>
          </Card>

          {a ? (
            <AnalysisBody
              ticket={ticket}
              analysis={a}
              onOpenSource={(refId) => setOpenSource(sourceByRef.get(refId) ?? null)}
            />
          ) : (
            <RecordedResolution ticket={ticket} />
          )}

          {a && a.retrieved.length > 0 && (
            <Card>
              <CardHeader
                title="Similar tickets and articles"
                subtitle="Found with hybrid semantic + keyword search, then reranked"
                icon={<FileSearch className="size-4" />}
              />
              <div className="grid gap-2.5 p-4 sm:grid-cols-2">
                {a.retrieved.map((s) => (
                  <SourceCard key={s.ref} source={s} cited={cited.has(s.ref)} onOpen={() => setOpenSource(s)} />
                ))}
              </div>
            </Card>
          )}
        </div>

        {/* right column */}
        <div className="space-y-5">
          {a ? <LabelsCard ticket={ticket} analysis={a} /> : <RecordedLabels ticket={ticket} />}

          {ticket.can_edit && ticket.status !== 'resolved' && (
            <Card className="p-4">
              <div className="space-y-2">
                <Button
                  variant="primary"
                  className="w-full"
                  icon={<CheckCircle2 className="size-4" />}
                  disabled={ticket.status === 'pending_review'}
                  onClick={() => setResolving(true)}
                >
                  Mark as resolved
                </Button>
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    icon={<RefreshCw className="size-4" />}
                    loading={reanalyze.isPending}
                    onClick={() => reanalyze.mutate()}
                  >
                    Re-run
                  </Button>
                  <Button icon={<MessagesSquare className="size-4" />} onClick={() => navigate(`/assistant?ticket=${ticket.ref}`)}>
                    Ask AI
                  </Button>
                </div>
                {ticket.status === 'pending_review' && (
                  <p className="pt-1 text-xs text-ink-3">You can resolve it once an admin has reviewed the draft.</p>
                )}
              </div>
            </Card>
          )}

          {user?.role === 'admin' && a?.review_status === 'pending_review' && (
            <Link
              to={`/approvals?ref=${ticket.ref}`}
              className="flex items-center justify-center gap-2 rounded-xl border border-warn/30 bg-warn/10 px-4 py-3 text-sm font-medium text-warn hover:bg-warn/15"
            >
              <ShieldAlert className="size-4" /> Review in approvals
            </Link>
          )}

          {a && <PipelineCard analysis={a} />}
        </div>
      </div>

      <SourceDrawer source={openSource} onClose={() => setOpenSource(null)} />
      {resolving && <ResolveModal ticket={ticket} onClose={() => setResolving(false)} />}
    </div>
  )
}

function AnalysisBody({
  ticket,
  analysis: a,
  onOpenSource,
}: {
  ticket: Ticket
  analysis: Analysis
  onOpenSource: (ref: string) => void
}) {
  const reply = a.draft_hidden ? '' : a.draft.customer_reply

  return (
    <>
      {a.review_status === 'pending_review' && (
        <Banner tone="warn" icon={<Hourglass className="size-4" />} title="Waiting for admin approval">
          This is a <b>critical</b> case{ticket.critical_reason ? ` (${ticket.critical_reason})` : ''}. The drafted
          resolution is hidden until an admin approves it. You'll get a notification as soon as they decide. Meanwhile the
          related tickets and articles are shown below.
        </Banner>
      )}
      {a.review_status === 'rejected' && (
        <Banner tone="danger" icon={<Ban className="size-4" />} title="Admin declined the AI draft">
          {a.decision?.comment || 'Handle this one manually and follow the escalation policy.'}
          {a.decision && <span className="mt-1 block text-xs opacity-75">- {a.decision.admin}</span>}
        </Banner>
      )}
      {(a.review_status === 'approved' || a.review_status === 'edited') && a.decision && (
        <Banner tone="ok" icon={<CheckCircle2 className="size-4" />} title={a.review_status === 'edited' ? 'Approved with changes' : 'Approved by admin'}>
          {a.decision.comment || 'You can share this resolution with the customer.'}
          <span className="mt-1 block text-xs opacity-75">- {a.decision.admin}</span>
        </Banner>
      )}
      {a.outcome === 'abstained' && (
        <Banner tone="neutral" icon={<AlertTriangle className="size-4" />} title="Not enough evidence to draft a fix">
          {a.abstain_reason} Escalate to a senior agent or use the related sources if any are listed.
        </Banner>
      )}
      {a.outcome === 'draft_unavailable' && (
        <Banner tone="neutral" icon={<AlertTriangle className="size-4" />} title="AI draft unavailable right now">
          The language model could not be reached. The similar tickets and articles below still apply, and you can re-run the
          analysis in a moment.
        </Banner>
      )}

      {!a.draft_hidden && a.steps.length > 0 && (
        <Card>
          <CardHeader
            title="Suggested resolution"
            subtitle="Every step cites the ticket or article it came from"
            icon={<ListChecks className="size-4" />}
            action={<ReviewBadge status={a.review_status} />}
          />
          <ol className="space-y-1 p-3">
            {a.steps.map((step, i) => (
              <li key={i} className="flex gap-3 rounded-lg px-2 py-2.5 hover:bg-raised/40">
                <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-raised text-xs font-semibold text-ink-2">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm leading-relaxed text-ink">{step.text}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {step.citations.map((c) => (
                      <CitationChip key={c} refId={c} onClick={() => onOpenSource(c)} />
                    ))}
                  </div>
                </div>
              </li>
            ))}
          </ol>
          {reply && (
            <div className="mx-4 mb-4 rounded-xl border border-line bg-panel p-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-semibold tracking-wide text-ink-3 uppercase">Suggested reply to customer</span>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(reply)
                    toast.success('Copied')
                  }}
                  className="flex items-center gap-1 text-xs text-ink-3 hover:text-ink"
                >
                  <Clipboard className="size-3.5" /> Copy
                </button>
              </div>
              <p className="text-sm leading-relaxed text-ink-2">{reply}</p>
            </div>
          )}
          <FeedbackBar analysis={a} ticketRef={ticket.ref} />
        </Card>
      )}

      {ticket.status === 'resolved' && ticket.resolution_steps.length > 0 && <RecordedResolution ticket={ticket} compact />}
    </>
  )
}

function Banner({
  tone,
  icon,
  title,
  children,
}: {
  tone: 'warn' | 'danger' | 'ok' | 'neutral'
  icon: React.ReactNode
  title: string
  children: React.ReactNode
}) {
  const styles = {
    warn: 'border-warn/25 bg-warn/[0.07] text-warn',
    danger: 'border-danger/25 bg-danger/[0.07] text-danger',
    ok: 'border-ok/25 bg-ok/[0.07] text-ok',
    neutral: 'border-line bg-card text-ink-2',
  }
  return (
    <div className={clsx('flex gap-3 rounded-xl border px-4 py-3.5', styles[tone])}>
      <span className="mt-0.5">{icon}</span>
      <div>
        <div className="text-sm font-semibold">{title}</div>
        <div className="mt-0.5 text-sm leading-relaxed text-ink-2">{children}</div>
      </div>
    </div>
  )
}

function FeedbackBar({ analysis, ticketRef }: { analysis: Analysis; ticketRef: string }) {
  const qc = useQueryClient()
  const { user } = useAuth()
  const send = useMutation({
    mutationFn: (rating: 'up' | 'down') => api.post(`/v1/analyses/${analysis.id}/feedback`, { rating }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ticket', ticketRef] })
      toast.success('Thanks for the feedback')
    },
  })
  if (user?.role === 'analyst') return null
  return (
    <div className="flex items-center justify-between border-t border-line px-5 py-3">
      <span className="text-xs text-ink-3">Was this helpful?</span>
      <div className="flex gap-1">
        {(['up', 'down'] as const).map((r) => (
          <button
            key={r}
            onClick={() => send.mutate(r)}
            className={clsx(
              'rounded-lg border p-1.5 transition',
              analysis.my_feedback === r
                ? r === 'up'
                  ? 'border-ok/40 bg-ok/10 text-ok'
                  : 'border-danger/40 bg-danger/10 text-danger'
                : 'border-line text-ink-3 hover:text-ink',
            )}
          >
            {r === 'up' ? <ThumbsUp className="size-3.5" /> : <ThumbsDown className="size-3.5" />}
          </button>
        ))}
      </div>
    </div>
  )
}

export function LabelsCard({ ticket, analysis: a }: { ticket: Ticket; analysis: Analysis }) {
  const p = a.parsed
  const rows: [string, React.ReactNode][] = [
    ['Category', ticket.category?.name ?? <span className="text-ink-3">Unclear</span>],
    ['Product', titleCase(ticket.product) || <span className="text-ink-3">-</span>],
    ['Severity', <SeverityBadge key="s" severity={ticket.severity} reason={ticket.critical_reason} />],
    ['Sentiment', <SentimentBadge key="t" sentiment={ticket.sentiment} />],
    ['Confidence', pct(p.confidence)],
  ]
  return (
    <Card>
      <CardHeader title="What the assistant understood" icon={<Cpu className="size-4" />} />
      <dl className="divide-y divide-line">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm">
            <dt className="text-ink-3">{k}</dt>
            <dd className="text-right text-ink">{v}</dd>
          </div>
        ))}
      </dl>
      {p.summary && <p className="border-t border-line px-5 py-3 text-xs leading-relaxed text-ink-2">{p.summary}</p>}
      {((p.rules_fired?.length ?? 0) > 0 || (p.pii_redacted?.length ?? 0) > 0 || (p.guidance_used?.length ?? 0) > 0) && (
        <div className="flex flex-wrap gap-1.5 border-t border-line px-5 py-3">
          {p.rules_fired?.map((r) => (
            <Badge key={r} tone="danger" title="A safety rule raised the severity">
              rule: {r.replace(/_/g, ' ')}
            </Badge>
          ))}
          {p.llm_severity && p.llm_severity !== ticket.severity && (
            <Badge tone="warn" title="What the model said before the rules">
              model said {p.llm_severity}
            </Badge>
          )}
          {p.pii_redacted?.map((k) => (
            <Badge key={k} tone="info" title="Masked before sending to the model">
              {k} masked
            </Badge>
          ))}
          {(p.guidance_used?.length ?? 0) > 0 && (
            <Badge tone="accent" title={p.guidance_used!.join('\n')}>
              {p.guidance_used!.length} analyst note{p.guidance_used!.length > 1 ? 's' : ''} used
            </Badge>
          )}
        </div>
      )}
    </Card>
  )
}

function RecordedLabels({ ticket }: { ticket: Ticket }) {
  const rows: [string, React.ReactNode][] = [
    ['Category', ticket.category?.name ?? '-'],
    ['Product', titleCase(ticket.product) || '-'],
    ['Severity', <SeverityBadge key="s" severity={ticket.severity} reason={ticket.critical_reason} />],
    ['Sentiment', <SentimentBadge key="t" sentiment={ticket.sentiment} />],
    ['Source', titleCase(ticket.source)],
  ]
  return (
    <Card>
      <CardHeader title="Ticket details" icon={<Cpu className="size-4" />} />
      <dl className="divide-y divide-line">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm">
            <dt className="text-ink-3">{k}</dt>
            <dd className="text-right text-ink">{v}</dd>
          </div>
        ))}
      </dl>
      {ticket.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-t border-line px-5 py-3">
          {ticket.tags.map((t) => (
            <Badge key={t}>{t}</Badge>
          ))}
        </div>
      )}
    </Card>
  )
}

function PipelineCard({ analysis: a }: { analysis: Analysis }) {
  const [open, setOpen] = useState(false)
  const stages = ['embed', 'classify', 'retrieve', 'draft'].filter((s) => a.timings[s] !== undefined)
  const total = a.timings.total || 1
  const colors: Record<string, string> = { embed: 'bg-info', classify: 'bg-accent', retrieve: 'bg-ok', draft: 'bg-warn' }
  return (
    <Card>
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between px-5 py-3.5 text-left">
        <span className="text-sm font-semibold">Pipeline details</span>
        <span className="flex items-center gap-2 text-xs text-ink-3">
          {((a.latency_ms ?? 0) / 1000).toFixed(1)}s
          <ChevronDown className={clsx('size-4 transition', open && 'rotate-180')} />
        </span>
      </button>
      <div className="px-5 pb-4">
        <div className="flex h-2 overflow-hidden rounded-full bg-raised">
          {stages.map((s) => (
            <div key={s} className={colors[s]} style={{ width: `${(a.timings[s] / total) * 100}%` }} title={`${s} ${a.timings[s]}ms`} />
          ))}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
          {stages.map((s) => (
            <span key={s} className="flex items-center gap-1.5 text-[11px] text-ink-3">
              <span className={clsx('size-2 rounded-full', colors[s])} />
              {s} {a.timings[s]}ms
            </span>
          ))}
        </div>
      </div>
      {open && (
        <dl className="space-y-1.5 border-t border-line px-5 py-3 text-xs">
          {[
            ['Model', a.model ?? '-'],
            ['Tokens', `${a.prompt_tokens} in / ${a.completion_tokens} out`],
            ['Est. cost', `$${a.cost_usd.toFixed(5)}`],
            ['Citations', a.citation_check.valid === undefined ? '-' : a.citation_check.valid ? (a.citation_check.retried ? 'valid after retry' : 'all valid') : 'some stripped'],
            ['Best similarity', pct(a.parsed.best_similarity, 1)],
            ['Trace id', a.trace_id ?? '-'],
          ].map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3">
              <dt className="text-ink-3">{k}</dt>
              <dd className="truncate font-mono text-ink-2">{v}</dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  )
}

function RecordedResolution({ ticket, compact }: { ticket: Ticket; compact?: boolean }) {
  if (ticket.resolution_steps.length === 0)
    return (
      <Card>
        <EmptyState icon={<ListChecks className="size-5" />} title="No analysis yet" text="This ticket has not been analysed." />
      </Card>
    )
  return (
    <Card>
      <CardHeader
        title={compact ? 'Resolution recorded by the agent' : 'How it was resolved'}
        subtitle={ticket.resolved_at ? `Resolved ${dateTime(ticket.resolved_at)}` : undefined}
        icon={<CheckCircle2 className="size-4 text-ok" />}
        action={ticket.is_searchable ? <Badge tone="ok">in knowledge pool</Badge> : <Badge>not searchable yet</Badge>}
      />
      <ol className="space-y-2 p-5">
        {ticket.resolution_steps.map((s, i) => (
          <li key={i} className="flex gap-3 text-sm text-ink-2">
            <span className="grid size-5 shrink-0 place-items-center rounded-full bg-raised text-[11px] font-semibold">{i + 1}</span>
            {s}
          </li>
        ))}
      </ol>
      {ticket.resolution_summary && (
        <p className="border-t border-line px-5 py-3 text-xs text-ink-3">{ticket.resolution_summary}</p>
      )}
    </Card>
  )
}

function ResolveModal({ ticket, onClose }: { ticket: Ticket; onClose: () => void }) {
  const qc = useQueryClient()
  const initial = ticket.analysis?.steps.map((s) => s.text) ?? []
  const [steps, setSteps] = useState<string[]>(initial.length ? initial : [''])
  const [summary, setSummary] = useState(ticket.analysis?.parsed.summary ?? '')

  const save = useMutation({
    mutationFn: () =>
      api.post<Ticket>(`/v1/tickets/${ticket.ref}/resolve`, {
        steps: steps.map((s) => s.trim()).filter(Boolean),
        summary: summary.trim() || undefined,
      }),
    onSuccess: (t) => {
      qc.setQueryData(['ticket', ticket.ref], t)
      qc.invalidateQueries({ queryKey: ['tickets'] })
      toast.success('Ticket resolved')
      onClose()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <Modal
      open
      onClose={onClose}
      title={`Resolve ${ticket.ref}`}
      width="max-w-2xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>
            Mark resolved
          </Button>
        </>
      }
    >
      <p className="mb-4 text-sm text-ink-3">
        Record the steps you actually took. An admin can later add this ticket to the searchable history.
      </p>
      <div className="space-y-2">
        {steps.map((s, i) => (
          <div key={i} className="flex gap-2">
            <span className="mt-2 w-5 text-right text-xs text-ink-3">{i + 1}.</span>
            <textarea
              rows={2}
              className="input"
              value={s}
              onChange={(e) => setSteps(steps.map((x, j) => (j === i ? e.target.value : x)))}
            />
            <button
              onClick={() => setSteps(steps.filter((_, j) => j !== i))}
              className="self-start rounded-md p-2 text-ink-3 hover:bg-raised hover:text-danger"
            >
              <Trash2 className="size-4" />
            </button>
          </div>
        ))}
        <Button size="sm" variant="ghost" icon={<Plus className="size-3.5" />} onClick={() => setSteps([...steps, ''])}>
          Add step
        </Button>
      </div>
      <div className="mt-4">
        <label className="label">Summary</label>
        <input className="input" value={summary} onChange={(e) => setSummary(e.target.value)} maxLength={1000} />
      </div>
    </Modal>
  )
}

function TicketSkeleton() {
  return (
    <div className="mx-auto max-w-5xl space-y-5 px-6 pt-16">
      <Skeleton className="h-5 w-64" />
      <Skeleton className="h-8 w-96" />
      <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
        <div className="space-y-5">
          <Skeleton className="h-32" />
          <Skeleton className="h-64" />
        </div>
        <Skeleton className="h-72" />
      </div>
    </div>
  )
}
