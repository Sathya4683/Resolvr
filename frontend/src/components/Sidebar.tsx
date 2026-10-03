import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  BookOpen,
  ClipboardCheck,
  FileBarChart2,
  FolderTree,
  Gauge,
  History,
  LogOut,
  MessagesSquare,
  PanelLeftClose,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  Users,
  DatabaseZap,
  type LucideIcon,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { NavLink, useNavigate, useParams } from 'react-router'
import { api } from '../lib/api'
import { ROLE_LABEL, useAuth } from '../lib/auth'
import { dayKey, dayLabel, timeOf } from '../lib/format'
import type { Role, TicketListItem } from '../lib/types'
import { SeverityIcon } from './badges'
import { Logo } from './Logo'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  roles: Role[]
  badgeKey?: 'approvals'
}

const NAV: NavItem[] = [
  { to: '/admin', label: 'Overview', icon: Gauge, roles: ['admin'] },
  { to: '/approvals', label: 'Approvals', icon: ShieldCheck, roles: ['admin'], badgeKey: 'approvals' },
  { to: '/reviews', label: 'Review queue', icon: ClipboardCheck, roles: ['analyst'] },
  { to: '/assistant', label: 'Assistant', icon: MessagesSquare, roles: ['support_agent', 'admin'] },
  { to: '/batch', label: 'Batch upload', icon: Upload, roles: ['support_agent', 'admin'] },
  { to: '/knowledge', label: 'Knowledge base', icon: BookOpen, roles: ['support_agent', 'admin', 'analyst'] },
  { to: '/quality', label: 'Quality', icon: Sparkles, roles: ['admin', 'analyst'] },
  { to: '/reports', label: 'Reports', icon: FileBarChart2, roles: ['admin', 'analyst'] },
  { to: '/categories', label: 'Categories', icon: FolderTree, roles: ['admin', 'analyst'] },
  { to: '/data', label: 'Data & imports', icon: DatabaseZap, roles: ['admin'] },
  { to: '/users', label: 'Users', icon: Users, roles: ['admin'] },
  { to: '/audit', label: 'Audit log', icon: History, roles: ['admin'] },
]

export function Sidebar({ onCollapse }: { onCollapse: () => void }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const role = user!.role
  const showTickets = role !== 'analyst'

  const tickets = useQuery({
    queryKey: ['tickets', 'sidebar', role],
    queryFn: () => api.get<TicketListItem[]>(`/v1/tickets?scope=${role === 'admin' ? 'all' : 'mine'}&limit=120`),
    enabled: showTickets,
    refetchInterval: 30_000,
  })

  const pending = useQuery({
    queryKey: ['approvals', 'count'],
    queryFn: () => api.get<{ pending: number }>('/v1/approvals/count'),
    enabled: role === 'admin',
    refetchInterval: 20_000,
  })

  const groups = useMemo(() => {
    const q = search.trim().toLowerCase()
    const items = (tickets.data ?? []).filter(
      (t) => !q || `${t.ref} ${t.subject ?? ''} ${t.snippet}`.toLowerCase().includes(q),
    )
    const byDay = new Map<string, { label: string; items: TicketListItem[] }>()
    for (const t of items) {
      const key = dayKey(t.created_at)
      if (!byDay.has(key)) byDay.set(key, { label: dayLabel(t.created_at), items: [] })
      byDay.get(key)!.items.push(t)
    }
    return [...byDay.values()]
  }, [tickets.data, search])

  const initials = user!.full_name
    .split(' ')
    .map((p) => p[0])
    .join('')
    .slice(0, 2)

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-line bg-panel">
      <div className="flex h-14 items-center justify-between px-4">
        <Logo />
        <button
          onClick={onCollapse}
          className="rounded-md p-1.5 text-ink-3 hover:bg-raised hover:text-ink"
          title="Hide sidebar"
        >
          <PanelLeftClose className="size-4" />
        </button>
      </div>

      {role !== 'analyst' && (
        <div className="px-3 pb-2">
          <button
            onClick={() => navigate('/tickets/new')}
            className="flex w-full items-center gap-2 rounded-lg border border-line bg-raised px-3 py-2 text-sm font-medium text-ink transition hover:border-line-strong hover:bg-hover"
          >
            <Plus className="size-4" />
            New ticket
          </button>
        </div>
      )}

      <nav className="space-y-0.5 px-3 py-2">
        {NAV.filter((n) => n.roles.includes(role)).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/admin'}
            className={({ isActive }) =>
              clsx(
                'group flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors',
                isActive ? 'bg-raised text-ink' : 'text-ink-2 hover:bg-raised/60 hover:text-ink',
              )
            }
          >
            <item.icon className="size-4 text-ink-3 group-hover:text-ink-2" />
            <span className="flex-1">{item.label}</span>
            {item.badgeKey === 'approvals' && (pending.data?.pending ?? 0) > 0 && (
              <span className="rounded-full bg-warn/15 px-1.5 text-[11px] font-semibold text-warn">
                {pending.data!.pending}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {showTickets && (
        <>
          <div className="mx-3 mt-2 border-t border-line pt-3">
            <div className="relative">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-3" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={role === 'admin' ? 'Search all tickets' : 'Search my tickets'}
                className="w-full rounded-lg border border-transparent bg-transparent py-1.5 pr-2 pl-8 text-xs text-ink placeholder:text-ink-3 outline-none hover:bg-raised/60 focus:border-line focus:bg-raised"
              />
            </div>
          </div>
          <div className="mt-1 flex-1 overflow-y-auto px-3 pb-3">
            {tickets.isLoading && <p className="px-2 py-3 text-xs text-ink-3">Loading tickets...</p>}
            {!tickets.isLoading && groups.length === 0 && (
              <p className="px-2 py-3 text-xs text-ink-3">{search ? 'No matches' : 'No tickets yet'}</p>
            )}
            {groups.map((g) => (
              <div key={g.label} className="mt-3">
                <div className="px-2 pb-1 text-[11px] font-semibold tracking-wide text-ink-3 uppercase">{g.label}</div>
                {g.items.map((t) => (
                  <TicketLink key={t.id} ticket={t} />
                ))}
              </div>
            ))}
          </div>
        </>
      )}
      {!showTickets && <div className="flex-1" />}

      <div className="border-t border-line p-3">
        <div className="flex items-center gap-3 rounded-lg px-2 py-1.5">
          <div className="grid size-8 place-items-center rounded-full bg-gradient-to-br from-accent to-accent-strong text-xs font-semibold text-white">
            {initials}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{user!.full_name}</div>
            <div className="text-xs text-ink-3">{ROLE_LABEL[role]}</div>
          </div>
          <button
            onClick={() => {
              logout()
              navigate('/login')
            }}
            className="rounded-md p-1.5 text-ink-3 hover:bg-raised hover:text-ink"
            title="Log out"
          >
            <LogOut className="size-4" />
          </button>
        </div>
      </div>
    </aside>
  )
}

function TicketLink({ ticket }: { ticket: TicketListItem }) {
  const { ref } = useParams()
  const active = ref === ticket.ref
  const pending = ticket.status === 'pending_review'
  return (
    <NavLink
      to={`/tickets/${ticket.ref}`}
      className={clsx(
        'group flex items-start gap-2.5 rounded-lg px-2 py-1.5 transition-colors',
        active ? 'bg-raised' : 'hover:bg-raised/60',
      )}
    >
      <span className="mt-[3px]">
        <SeverityIcon severity={ticket.severity} />
      </span>
      <div className="min-w-0 flex-1">
        <div className={clsx('truncate text-[13px]', active ? 'text-ink' : 'text-ink-2 group-hover:text-ink')}>
          {ticket.subject || ticket.snippet}
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-ink-3">
          <span className="font-mono">{ticket.ref}</span>
          <span>·</span>
          <span>{timeOf(ticket.created_at)}</span>
          {pending && <span className="text-warn">· awaiting approval</span>}
          {ticket.status === 'resolved' && <span className="text-ok/80">· resolved</span>}
        </div>
      </div>
    </NavLink>
  )
}
