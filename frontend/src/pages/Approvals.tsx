import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Check, CheckCheck, Clock, Inbox, PenLine, Plus, ShieldCheck, Trash2, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { ReviewBadge, SeverityIcon } from '../components/badges'
import { CitationChip, SourceCard, SourceDrawer } from '../components/sources'
import { Badge, Button, Card, CardHeader, EmptyState, Mono, PageHeader, Skeleton, Tabs } from '../components/ui'
import { api } from '../lib/api'
import { dateTime, titleCase } from '../lib/format'
import type { ApprovalItem, Source, Step, TicketDetail } from '../lib/types'
import { LabelsCard } from './TicketDetail'

const SLA_MINUTES = 30

function waiting(minutes: number) {
  if (minutes < 60) return `${minutes}m`
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
  return `${Math.floor(minutes / 1440)}d`
}

export default function Approvals() {
  const [params, setParams] = useSearchParams()
  const [tab, setTab] = useState<'pending' | 'decided'>('pending')
  const selectedRef = params.get('ref')

  const pending = useQuery({
    queryKey: ['approvals', 'pending'],
    queryFn: () => api.get<ApprovalItem[]>('/v1/approvals?state=pending'),
    refetchInterval: 15_000,
  })
  const decided = useQuery({
    queryKey: ['approvals', 'decided'],
    queryFn: () => api.get<ApprovalItem[]>('/v1/approvals?state=decided'),
    enabled: tab === 'decided',
  })

  //open the first case automatically so the admin can start straight away
  useEffect(() => {
    if (tab === 'pending' && !selectedRef && pending.data?.length) {
      setParams({ ref: pending.data[0].ticket_ref }, { replace: true })
    }
  }, [tab, selectedRef, pending.data, setParams])

  return (
    <div className="mx-auto max-w-7xl px-6 pt-16 pb-16">
      <PageHeader
        title="Approvals"
        subtitle="Legal, regulatory, fraud, privacy and compensation cases need an admin's sign-off before the agent sees the draft."
        actions={
          <Tabs
            value={tab}
            onChange={setTab}
            items={[
              { value: 'pending', label: `Pending${pending.data ? ` (${pending.data.length})` : ''}` },
              { value: 'decided', label: 'Decided' },
            ]}
          />
        }
      />

      {tab === 'decided' ? (
        <DecidedTable items={decided.data} loading={decided.isLoading} />
      ) : pending.isLoading ? (
        <Skeleton className="h-96" />
      ) : !pending.data?.length ? (
        <Card>
          <EmptyState
            icon={<CheckCheck className="size-5" />}
            title="Nothing waiting for approval"
            text="Critical cases will show up here as soon as an agent raises one. You'll also get a push notification."
          />
        </Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[340px_1fr]">
          <div className="space-y-2">
            {pending.data.map((item) => (
              <button
                key={item.analysis_id}
                onClick={() => setParams({ ref: item.ticket_ref })}
                className={clsx(
                  'w-full rounded-xl border p-3.5 text-left transition',
                  selectedRef === item.ticket_ref
                    ? 'border-accent/50 bg-accent/[0.06]'
                    : 'border-line bg-card hover:border-line-strong',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <SeverityIcon severity={item.severity} />
                    <Mono className="text-ink-2">{item.ticket_ref}</Mono>
                    {item.critical_reason && <Badge tone="danger">{item.critical_reason}</Badge>}
                  </div>
                  <span
                    className={clsx(
                      'flex items-center gap-1 text-xs tabular-nums',
                      item.waiting_minutes >= SLA_MINUTES ? 'text-danger' : 'text-ink-3',
                    )}
                    title="Time waiting for a decision"
                  >
                    <Clock className="size-3" />
                    {waiting(item.waiting_minutes)}
                  </span>
                </div>
                <div className="mt-2 line-clamp-1 text-sm font-medium">{item.subject || item.category || 'Complaint'}</div>
                <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-ink-3">{item.snippet}</div>
                <div className="mt-2 text-[11px] text-ink-3">Raised by {item.raised_by ?? 'unknown'}</div>
              </button>
            ))}
          </div>
          {selectedRef ? (
            <ReviewPanel key={selectedRef} ticketRef={selectedRef} />
          ) : (
            <Card>
              <EmptyState icon={<Inbox className="size-5" />} title="Pick a case" />
            </Card>
          )}
        </div>
      )}
    </div>
  )
}

function ReviewPanel({ ticketRef }: { ticketRef: string }) {
  const qc = useQueryClient()
  const [, setParams] = useSearchParams()
  const [openSource, setOpenSource] = useState<Source | null>(null)
  const [steps, setSteps] = useState<Step[] | null>(null)
  const [comment, setComment] = useState('')

  const { data: ticket, isLoading } = useQuery({
    queryKey: ['ticket', ticketRef],
    queryFn: () => api.get<TicketDetail>(`/v1/tickets/${ticketRef}`),
  })
  const a = ticket?.analysis
  const original = useMemo(() => a?.draft.steps ?? [], [a])
  useEffect(() => setSteps(original.map((s) => ({ ...s, citations: [...s.citations] }))), [original])

  const edited = steps !== null && JSON.stringify(steps) !== JSON.stringify(original)
  const refs = a?.retrieved.map((s) => s.ref) ?? []

  const decide = useMutation({
    mutationFn: (action: 'approve' | 'edit' | 'reject') =>
      api.post(`/v1/approvals/${a!.id}/decision`, {
        action,
        comment: comment.trim() || undefined,
        steps: action === 'edit' ? steps!.filter((s) => s.text.trim()) : undefined,
      }),
    onSuccess: (_, action) => {
      toast.success(action === 'reject' ? 'Draft declined, agent notified' : 'Approved, agent notified')
      qc.invalidateQueries({ queryKey: ['approvals'] })
      qc.invalidateQueries({ queryKey: ['ticket', ticketRef] })
      qc.invalidateQueries({ queryKey: ['tickets'] })
      setParams({}, { replace: true })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  if (isLoading || !ticket || !a || steps === null) return <Skeleton className="h-[600px]" />
  if (a.review_status !== 'pending_review')
    return (
      <Card>
        <EmptyState icon={<Check className="size-5" />} title="Already decided" text="Someone has already reviewed this case." />
      </Card>
    )

  const update = (i: number, patch: Partial<Step>) => setSteps(steps.map((s, j) => (j === i ? { ...s, ...patch } : s)))

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              <Mono className="text-ink-2">{ticket.ref}</Mono> {ticket.subject || 'Complaint'}
            </span>
          }
          subtitle={`Raised by ${ticket.created_by?.full_name ?? 'unknown'} · ${dateTime(ticket.created_at)}`}
          action={<ReviewBadge status={a.review_status} />}
        />
        <p className="px-5 py-4 text-[15px] leading-relaxed whitespace-pre-wrap">{ticket.complaint}</p>
      </Card>

      <div className="grid gap-5 xl:grid-cols-[1fr_300px]">
        <div className="min-w-0 space-y-5">
          <Card>
            <CardHeader
              title="Drafted resolution"
              subtitle={edited ? 'You have edited this draft' : 'Edit any step before approving if needed'}
              icon={<PenLine className="size-4" />}
            />
            {a.outcome !== 'drafted' && (
              <p className="border-b border-line px-5 py-3 text-sm text-ink-3">
                {a.outcome === 'abstained'
                  ? `The assistant did not draft steps: ${a.abstain_reason}`
                  : 'The AI draft was unavailable.'}{' '}
                Add the steps the agent should follow below.
              </p>
            )}
            <div className="space-y-3 p-4">
              {steps.map((step, i) => (
                <div key={i} className="rounded-xl border border-line bg-panel p-3">
                  <div className="flex gap-3">
                    <span className="mt-2 grid size-6 shrink-0 place-items-center rounded-full bg-raised text-xs font-semibold text-ink-2">
                      {i + 1}
                    </span>
                    <textarea
                      rows={2}
                      value={step.text}
                      onChange={(e) => update(i, { text: e.target.value })}
                      className="input resize-y bg-card"
                    />
                    <button
                      onClick={() => setSteps(steps.filter((_, j) => j !== i))}
                      className="self-start rounded-md p-2 text-ink-3 hover:bg-raised hover:text-danger"
                      title="Remove step"
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </div>
                  <div className="mt-2 ml-9 flex flex-wrap items-center gap-1.5">
                    {step.citations.map((c) => (
                      <span key={c} className="group inline-flex items-center">
                        <CitationChip refId={c} onClick={() => setOpenSource(a.retrieved.find((s) => s.ref === c) ?? null)} />
                        <button
                          onClick={() => update(i, { citations: step.citations.filter((x) => x !== c) })}
                          className="ml-0.5 rounded p-0.5 text-ink-3 opacity-0 transition group-hover:opacity-100 hover:text-danger"
                          title="Remove citation"
                        >
                          <X className="size-3" />
                        </button>
                      </span>
                    ))}
                    <select
                      value=""
                      onChange={(e) => e.target.value && update(i, { citations: [...step.citations, e.target.value] })}
                      className="rounded-md border border-dashed border-line bg-transparent px-1.5 py-0.5 text-[11px] text-ink-3 outline-none hover:border-line-strong"
                    >
                      <option value="">+ cite</option>
                      {refs
                        .filter((r) => !step.citations.includes(r))
                        .map((r) => (
                          <option key={r} value={r}>
                            {r}
                          </option>
                        ))}
                    </select>
                  </div>
                </div>
              ))}
              <Button
                size="sm"
                variant="ghost"
                icon={<Plus className="size-3.5" />}
                onClick={() => setSteps([...steps, { text: '', citations: [] }])}
              >
                Add step
              </Button>
            </div>
          </Card>

          <Card>
            <CardHeader title="Sources the draft could use" icon={<ShieldCheck className="size-4" />} />
            <div className="grid gap-2.5 p-4 sm:grid-cols-2">
              {a.retrieved.map((s) => (
                <SourceCard
                  key={s.ref}
                  source={s}
                  cited={steps.some((st) => st.citations.includes(s.ref))}
                  onOpen={() => setOpenSource(s)}
                />
              ))}
            </div>
          </Card>
        </div>

        <div className="space-y-5">
          <LabelsCard ticket={ticket} analysis={a} />
          <Card className="p-4">
            <label className="label">Note to the agent</label>
            <textarea
              rows={3}
              className="input"
              placeholder="Required when declining. Shown to the agent with the decision."
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
            <div className="mt-4 space-y-2">
              {edited ? (
                <Button
                  variant="primary"
                  className="w-full"
                  loading={decide.isPending && decide.variables === 'edit'}
                  onClick={() => decide.mutate('edit')}
                  icon={<PenLine className="size-4" />}
                >
                  Approve with changes
                </Button>
              ) : (
                <Button
                  variant="primary"
                  className="w-full"
                  disabled={steps.length === 0}
                  loading={decide.isPending && decide.variables === 'approve'}
                  onClick={() => decide.mutate('approve')}
                  icon={<Check className="size-4" />}
                >
                  Approve
                </Button>
              )}
              <Button
                variant="danger"
                className="w-full"
                disabled={!comment.trim()}
                loading={decide.isPending && decide.variables === 'reject'}
                onClick={() => decide.mutate('reject')}
                icon={<X className="size-4" />}
              >
                Decline draft
              </Button>
              <p className="pt-1 text-center text-[11px] text-ink-3">
                The agent is notified in the app and on the support ntfy topic.
              </p>
            </div>
          </Card>
        </div>
      </div>
      <SourceDrawer source={openSource} onClose={() => setOpenSource(null)} />
    </div>
  )
}

function DecidedTable({ items, loading }: { items?: ApprovalItem[]; loading: boolean }) {
  if (loading) return <Skeleton className="h-64" />
  if (!items?.length)
    return (
      <Card>
        <EmptyState icon={<Inbox className="size-5" />} title="No decisions yet" />
      </Card>
    )
  return (
    <Card className="overflow-hidden">
      <table className="w-full text-sm">
        <thead className="border-b border-line bg-panel text-left text-xs text-ink-3">
          <tr>
            <th className="px-4 py-2.5 font-medium">Ticket</th>
            <th className="px-4 py-2.5 font-medium">Reason</th>
            <th className="px-4 py-2.5 font-medium">Decision</th>
            <th className="px-4 py-2.5 font-medium">By</th>
            <th className="px-4 py-2.5 font-medium">When</th>
            <th className="px-4 py-2.5 font-medium">Note</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {items.map((i) => (
            <tr key={`${i.analysis_id}-${i.decided_at}`} className="hover:bg-raised/40">
              <td className="px-4 py-3">
                <Link to={`/tickets/${i.ticket_ref}`} className="font-mono text-xs text-accent hover:underline">
                  {i.ticket_ref}
                </Link>
                <div className="line-clamp-1 max-w-xs text-xs text-ink-3">{i.subject || i.snippet}</div>
              </td>
              <td className="px-4 py-3 text-ink-2">{titleCase(i.critical_reason) || '-'}</td>
              <td className="px-4 py-3">
                <ReviewBadge status={i.review_status} />
              </td>
              <td className="px-4 py-3 text-ink-2">{i.decided_by}</td>
              <td className="px-4 py-3 text-xs text-ink-3">{i.decided_at && dateTime(i.decided_at)}</td>
              <td className="max-w-xs px-4 py-3 text-xs text-ink-3">{i.comment || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}
