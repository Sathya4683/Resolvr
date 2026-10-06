import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  BookOpen,
  CheckCircle2,
  Coins,
  ExternalLink,
  Gauge,
  Inbox,
  ShieldAlert,
  ThumbsUp,
  Timer,
} from 'lucide-react'
import { Link } from 'react-router'
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from 'recharts'
import type { NameType, ValueType } from 'recharts/types/component/DefaultTooltipContent'
import { SeverityIcon } from '../components/badges'
import { Card, CardHeader, Mono, PageHeader, Skeleton, Stat } from '../components/ui'
import { api, API_URL } from '../lib/api'
import { pct, titleCase } from '../lib/format'
import type { ApprovalItem, Severity } from '../lib/types'

interface OverviewData {
  kpis: {
    created_today: number
    resolved_today: number
    pending_approvals: number
    searchable_tickets: number
    kb_articles: number
    analyses: number
    abstention_rate: number | null
    avg_latency_ms: number | null
    tokens: number
    cost_usd: number
    thumbs_up_rate: number | null
    feedback_count: number
    analyst_accuracy: number | null
    analyst_reviews: number
  }
  per_day: { day: string; low: number; medium: number; high: number; critical: number }[]
  categories: { name: string; count: number }[]
  outcomes: Record<string, number>
}

//severity is a status, so it uses the fixed status steps (validated against the dark surface)
const SEVERITY_COLORS: Record<Severity, string> = {
  low: '#7d8594',
  medium: '#fab219',
  high: '#ec835a',
  critical: '#d03b3b',
}
const SEVERITIES: Severity[] = ['low', 'medium', 'high', 'critical']
const SURFACE = '#14171c'
const AXIS = { fill: '#6c7380', fontSize: 12 }

//on the server everything sits behind one domain (api on the same origin, grafana on a subdomain)
const MONITORING = API_URL
  ? [
      { label: 'Grafana dashboards', url: 'http://localhost:3001' },
      { label: 'Prometheus', url: 'http://localhost:9091' },
      { label: 'Mailpit (dev inbox)', url: 'http://localhost:8026' },
      { label: 'API docs', url: `${API_URL}/docs` },
    ]
  : [
      { label: 'Grafana dashboards', url: `https://grafana.${window.location.host}` },
      { label: 'API docs', url: '/docs' },
    ]

function dayName(iso: string) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })
}

function SeverityTooltip({ active, payload, label }: TooltipContentProps<ValueType, NameType>) {
  if (!active || !payload?.length) return null
  const total = payload.reduce((sum, p) => sum + Number(p.value ?? 0), 0)
  return (
    <div className="rounded-lg border border-line bg-raised px-3 py-2 text-xs shadow-xl">
      <div className="mb-1.5 font-medium text-ink">{dayName(String(label))}</div>
      {[...payload].reverse().map((p) => (
        <div key={String(p.dataKey)} className="flex items-center justify-between gap-6 py-0.5 text-ink-2">
          <span className="flex items-center gap-2">
            <span className="size-2.5 rounded-sm" style={{ background: SEVERITY_COLORS[p.dataKey as Severity] }} />
            {titleCase(String(p.dataKey))}
          </span>
          <span className="text-ink tabular-nums">{p.value}</span>
        </div>
      ))}
      <div className="mt-1 flex justify-between border-t border-line pt-1 text-ink-2">
        <span>Total</span>
        <span className="text-ink tabular-nums">{total}</span>
      </div>
    </div>
  )
}

export default function Overview() {
  const { data, isLoading } = useQuery({
    queryKey: ['overview'],
    queryFn: () => api.get<OverviewData>('/v1/admin/overview?days=7'),
    refetchInterval: 30_000,
  })
  const pending = useQuery({
    queryKey: ['approvals', 'pending'],
    queryFn: () => api.get<ApprovalItem[]>('/v1/approvals?state=pending'),
  })

  if (isLoading || !data)
    return (
      <div className="mx-auto max-w-7xl space-y-5 px-6 pt-16">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      </div>
    )

  const k = data.kpis
  return (
    <div className="mx-auto max-w-7xl px-6 pt-16 pb-16">
      <PageHeader title="Overview" subtitle="Today's desk at a glance, plus the last 7 days of AI quality." />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Tickets today" value={k.created_today} hint={`${k.resolved_today} resolved today`} icon={<Inbox className="size-3.5" />} />
        <Link to="/approvals">
          <Stat
            label="Waiting for approval"
            value={k.pending_approvals}
            hint="Critical cases need sign-off"
            icon={<ShieldAlert className="size-3.5" />}
            tone={k.pending_approvals ? 'warn' : 'neutral'}
          />
        </Link>
        <Stat
          label="Agent thumbs-up rate"
          value={pct(k.thumbs_up_rate)}
          hint={`${k.feedback_count} ratings, last 7 days`}
          icon={<ThumbsUp className="size-3.5" />}
          tone="ok"
        />
        <Stat
          label="Analyst accuracy"
          value={pct(k.analyst_accuracy)}
          hint={`${k.analyst_reviews} reviews marked correct`}
          icon={<CheckCircle2 className="size-3.5" />}
          tone="accent"
        />
        <Stat
          label="Avg analysis time"
          value={k.avg_latency_ms ? `${(k.avg_latency_ms / 1000).toFixed(1)}s` : '-'}
          hint={`${k.analyses} analyses, last 7 days`}
          icon={<Timer className="size-3.5" />}
        />
        <Stat
          label="Abstention rate"
          value={pct(k.abstention_rate)}
          hint="Refused to draft without evidence"
          icon={<Gauge className="size-3.5" />}
        />
        <Stat
          label="LLM cost (est.)"
          value={`$${k.cost_usd.toFixed(3)}`}
          hint={`${k.tokens.toLocaleString()} tokens, last 7 days`}
          icon={<Coins className="size-3.5" />}
        />
        <Stat
          label="Knowledge pool"
          value={k.searchable_tickets + k.kb_articles}
          hint={`${k.searchable_tickets} tickets · ${k.kb_articles} articles`}
          icon={<BookOpen className="size-3.5" />}
        />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader title="Tickets per day by severity" subtitle="Includes imported history and new complaints" icon={<Activity className="size-4" />} />
          <div className="flex flex-wrap gap-4 px-5 pt-4 text-xs text-ink-2">
            {SEVERITIES.map((s) => (
              <span key={s} className="flex items-center gap-2">
                <span className="size-2.5 rounded-sm" style={{ background: SEVERITY_COLORS[s] }} />
                {titleCase(s)}
              </span>
            ))}
          </div>
          <div className="h-72 px-2 pt-2 pb-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.per_day} margin={{ top: 8, right: 16, left: 0, bottom: 0 }} barCategoryGap="35%">
                <CartesianGrid vertical={false} stroke="#232831" />
                <XAxis dataKey="day" tickFormatter={dayName} tick={AXIS} axisLine={false} tickLine={false} />
                <YAxis tick={AXIS} axisLine={false} tickLine={false} width={40} allowDecimals={false} />
                <Tooltip content={SeverityTooltip} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
                {SEVERITIES.map((s, i) => (
                  <Bar
                    key={s}
                    dataKey={s}
                    stackId="sev"
                    fill={SEVERITY_COLORS[s]}
                    stroke={SURFACE}
                    strokeWidth={2}
                    maxBarSize={56}
                    radius={i === SEVERITIES.length - 1 ? [4, 4, 0, 0] : 0}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <CardHeader title="Top categories" subtitle="Last 7 days" />
          <div className="px-2 py-3" style={{ height: Math.max(220, data.categories.length * 40 + 24) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.categories} layout="vertical" margin={{ top: 4, right: 40, left: 8, bottom: 4 }}>
                <XAxis type="number" hide />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={200}
                  tick={{ ...AXIS, fill: '#a9afba' }}
                  interval={0}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  cursor={{ fill: 'rgba(255,255,255,0.03)' }}
                  contentStyle={{ background: '#1a1e25', border: '1px solid #232831', borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: '#e8eaef' }}
                  itemStyle={{ color: '#a9afba' }}
                  formatter={(v) => [v, 'Tickets']}
                />
                <Bar dataKey="count" fill="#8083ff" radius={[0, 4, 4, 0]} maxBarSize={18}>
                  <LabelList dataKey="count" position="right" style={{ fill: '#a9afba', fontSize: 12 }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader
            title="Waiting for approval"
            subtitle="Oldest first"
            icon={<ShieldAlert className="size-4" />}
            action={
              <Link to="/approvals" className="text-xs text-accent hover:underline">
                Open queue
              </Link>
            }
          />
          {pending.data?.length ? (
            <ul className="divide-y divide-line">
              {pending.data.slice(0, 6).map((p) => (
                <li key={p.analysis_id}>
                  <Link to={`/approvals?ref=${p.ticket_ref}`} className="flex items-center gap-3 px-5 py-3 hover:bg-raised/40">
                    <SeverityIcon severity={p.severity} />
                    <Mono className="text-ink-2">{p.ticket_ref}</Mono>
                    <span className="min-w-0 flex-1 truncate text-sm text-ink-2">{p.snippet}</span>
                    <span className="text-xs text-ink-3">{titleCase(p.critical_reason)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-5 py-8 text-center text-sm text-ink-3">Nothing waiting, nice.</p>
          )}
        </Card>

        <Card>
          <CardHeader title="Monitoring" subtitle="Local tools started by docker compose" />
          <ul className="divide-y divide-line">
            {MONITORING.map((m) => (
              <li key={m.url}>
                <a
                  href={m.url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center justify-between px-5 py-3 text-sm text-ink-2 hover:bg-raised/40 hover:text-ink"
                >
                  {m.label}
                  <span className="flex items-center gap-2 text-xs text-ink-3">
                    {m.url.replace('http://', '')} <ExternalLink className="size-3.5" />
                  </span>
                </a>
              </li>
            ))}
          </ul>
          <div className="border-t border-line px-5 py-3 text-xs text-ink-3">
            Pipeline outcomes (7 days):{' '}
            {Object.entries(data.outcomes)
              .map(([k2, v]) => `${titleCase(k2)} ${v}`)
              .join(' · ') || 'none yet'}
          </div>
        </Card>
      </div>
    </div>
  )
}
