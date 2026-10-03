import clsx from 'clsx'
import { AlertOctagon, AlertTriangle, CheckCircle2, Circle, Clock, Frown, Meh, ShieldAlert, Smile, XCircle, Zap } from 'lucide-react'
import { titleCase } from '../lib/format'
import type { ReviewStatus, Severity } from '../lib/types'
import { Badge, type Tone } from './ui'

const SEVERITY: Record<Severity, { tone: Tone; label: string }> = {
  low: { tone: 'neutral', label: 'Low' },
  medium: { tone: 'warn', label: 'Medium' },
  high: { tone: 'high', label: 'High' },
  critical: { tone: 'danger', label: 'Critical' },
}

//priority bars like linear / jira: one, two or three bars, and a red "!" tile for critical
export function SeverityIcon({ severity }: { severity: Severity | null }) {
  if (severity === 'critical')
    return (
      <span
        title="Critical"
        className="grid size-3.5 shrink-0 place-items-center rounded-[3px] bg-danger text-[10px] leading-none font-bold text-bg"
      >
        !
      </span>
    )
  const level = severity ? { low: 1, medium: 2, high: 3 }[severity] : 0
  const color = { 1: 'bg-ink-2', 2: 'bg-warn', 3: 'bg-high' }[level] ?? 'bg-ink-3'
  return (
    <span title={severity ? `${severity} severity` : 'Not rated'} className="flex h-3.5 w-3.5 shrink-0 items-end gap-[2px]">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={clsx('w-[3px] rounded-[1px]', i < level ? color : 'bg-line-strong')}
          style={{ height: `${5 + i * 3.5}px` }}
        />
      ))}
    </span>
  )
}

export function SeverityBadge({ severity, reason }: { severity: Severity | null; reason?: string | null }) {
  if (!severity) return <Badge>Unrated</Badge>
  const s = SEVERITY[severity]
  return (
    <Badge tone={s.tone} icon={severity === 'critical' ? <ShieldAlert className="size-3" /> : <Zap className="size-3" />}>
      {s.label}
      {reason && <span className="opacity-75">· {reason}</span>}
    </Badge>
  )
}

export function SentimentBadge({ sentiment }: { sentiment: string | null }) {
  if (!sentiment) return null
  const map: Record<string, { tone: Tone; icon: React.ReactNode }> = {
    angry: { tone: 'danger', icon: <AlertOctagon className="size-3" /> },
    frustrated: { tone: 'high', icon: <Frown className="size-3" /> },
    neutral: { tone: 'neutral', icon: <Meh className="size-3" /> },
    positive: { tone: 'ok', icon: <Smile className="size-3" /> },
  }
  const m = map[sentiment] ?? map.neutral
  return (
    <Badge tone={m.tone} icon={m.icon}>
      {titleCase(sentiment)}
    </Badge>
  )
}

export function StatusBadge({ status, review }: { status: string; review?: ReviewStatus | null }) {
  if (status === 'pending_review' || review === 'pending_review')
    return (
      <Badge tone="warn" icon={<Clock className="size-3" />}>
        Awaiting approval
      </Badge>
    )
  if (status === 'resolved')
    return (
      <Badge tone="ok" icon={<CheckCircle2 className="size-3" />}>
        Resolved
      </Badge>
    )
  if (review === 'rejected')
    return (
      <Badge tone="danger" icon={<XCircle className="size-3" />}>
        Draft declined
      </Badge>
    )
  return (
    <Badge tone="info" icon={<Circle className="size-3" />}>
      Open
    </Badge>
  )
}

export function ReviewBadge({ status }: { status: ReviewStatus }) {
  const map: Record<ReviewStatus, { tone: Tone; label: string }> = {
    auto_approved: { tone: 'neutral', label: 'Auto approved' },
    pending_review: { tone: 'warn', label: 'Pending review' },
    approved: { tone: 'ok', label: 'Approved' },
    edited: { tone: 'accent', label: 'Approved with changes' },
    rejected: { tone: 'danger', label: 'Declined' },
  }
  const m = map[status]
  return (
    <Badge tone={m.tone} icon={status === 'pending_review' ? <AlertTriangle className="size-3" /> : undefined}>
      {m.label}
    </Badge>
  )
}
