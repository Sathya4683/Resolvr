import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { History, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Badge, Button, Card, Modal, Mono, PageHeader, Skeleton, Tabs } from '../components/ui'
import { api } from '../lib/api'
import { ROLE_LABEL, useAuth } from '../lib/auth'
import { dateTime, timeAgo } from '../lib/format'
import type { Role, User } from '../lib/types'

export function Users() {
  const { user: me } = useAuth()
  const qc = useQueryClient()
  const [creating, setCreating] = useState(false)
  const { data, isLoading } = useQuery({ queryKey: ['users'], queryFn: () => api.get<User[]>('/v1/users') })

  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<User> }) => api.patch<User>(`/v1/users/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <div className="mx-auto max-w-5xl px-6 pt-16 pb-16">
      <PageHeader
        title="Users"
        subtitle="Support agents, admins and analysts. Roles are enforced by the API on every request."
        actions={
          <Button variant="primary" icon={<UserPlus className="size-4" />} onClick={() => setCreating(true)}>
            Add user
          </Button>
        }
      />
      {isLoading ? (
        <Skeleton className="h-72" />
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-line bg-panel text-left text-xs text-ink-3">
              <tr>
                <th className="px-4 py-2.5 font-medium">Name</th>
                <th className="px-4 py-2.5 font-medium">Role</th>
                <th className="px-4 py-2.5 font-medium">Last login</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data?.map((u) => (
                <tr key={u.id} className="hover:bg-raised/40">
                  <td className="px-4 py-3">
                    <div className="font-medium">{u.full_name}</div>
                    <div className="text-xs text-ink-3">
                      <Mono>{u.username}</Mono> {u.email && `· ${u.email}`}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <select
                      className="rounded-md border border-line bg-panel px-2 py-1 text-xs text-ink-2 outline-none disabled:opacity-60"
                      value={u.role}
                      disabled={u.id === me?.id}
                      onChange={(e) => update.mutate({ id: u.id, body: { role: e.target.value as Role } })}
                    >
                      {(['support_agent', 'admin', 'analyst'] as Role[]).map((r) => (
                        <option key={r} value={r}>
                          {ROLE_LABEL[r]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3 text-xs text-ink-3">{u.last_login_at ? timeAgo(u.last_login_at) : 'never'}</td>
                  <td className="px-4 py-3">
                    <button
                      disabled={u.id === me?.id}
                      onClick={() => update.mutate({ id: u.id, body: { is_active: !u.is_active } })}
                      title={u.id === me?.id ? "You can't disable yourself" : 'Toggle access'}
                    >
                      {u.is_active ? <Badge tone="ok">Active</Badge> : <Badge tone="danger">Disabled</Badge>}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {creating && <NewUser onClose={() => setCreating(false)} />}
    </div>
  )
}

function NewUser({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ username: '', full_name: '', email: '', role: 'support_agent' as Role, password: '' })
  const save = useMutation({
    mutationFn: () => api.post('/v1/users', { ...form, email: form.email || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['users'] })
      toast.success('User created')
      onClose()
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const field = (key: keyof typeof form, label: string, type = 'text') => (
    <div>
      <label className="label">{label}</label>
      <input
        className="input"
        type={type}
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
      />
    </div>
  )
  return (
    <Modal
      open
      onClose={onClose}
      title="Add user"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>
            Create
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {field('full_name', 'Full name')}
        <div className="grid grid-cols-2 gap-3">
          {field('username', 'Username')}
          <div>
            <label className="label">Role</label>
            <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              {(['support_agent', 'admin', 'analyst'] as Role[]).map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </select>
          </div>
        </div>
        {field('email', 'Email (optional)', 'email')}
        {field('password', 'Temporary password (min 8 characters)', 'password')}
      </div>
    </Modal>
  )
}

interface AuditRow {
  id: number
  action: string
  user: string
  role: Role | null
  entity_type: string | null
  entity_id: string | null
  details: Record<string, unknown>
  created_at: string
}

const AUDIT_FILTERS = [
  { value: '', label: 'All' },
  { value: 'approval', label: 'Approvals' },
  { value: 'kb', label: 'Knowledge' },
  { value: 'category', label: 'Categories' },
  { value: 'data', label: 'Imports' },
  { value: 'ticket', label: 'Tickets' },
  { value: 'report', label: 'Reports' },
  { value: 'user', label: 'Users' },
]

export function Audit() {
  const [filter, setFilter] = useState('')
  const { data, isLoading } = useQuery({
    queryKey: ['audit', filter],
    queryFn: () => api.get<AuditRow[]>(`/v1/audit?limit=200${filter ? `&action=${filter}` : ''}`),
  })
  return (
    <div className="mx-auto max-w-6xl px-6 pt-16 pb-16">
      <PageHeader
        title="Audit log"
        subtitle="Every sensitive action, who did it and when."
        actions={<Tabs value={filter} onChange={setFilter} items={AUDIT_FILTERS} />}
      />
      {isLoading ? (
        <Skeleton className="h-96" />
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-line bg-panel text-left text-xs text-ink-3">
              <tr>
                <th className="px-4 py-2.5 font-medium">When</th>
                <th className="px-4 py-2.5 font-medium">Who</th>
                <th className="px-4 py-2.5 font-medium">Action</th>
                <th className="px-4 py-2.5 font-medium">Target</th>
                <th className="px-4 py-2.5 font-medium">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data?.map((a) => (
                <tr key={a.id} className="align-top hover:bg-raised/40">
                  <td className="px-4 py-2.5 text-xs whitespace-nowrap text-ink-3">{dateTime(a.created_at)}</td>
                  <td className="px-4 py-2.5">
                    <div className="text-ink-2">{a.user}</div>
                    {a.role && <div className="text-[11px] text-ink-3">{ROLE_LABEL[a.role]}</div>}
                  </td>
                  <td className="px-4 py-2.5">
                    <Badge icon={<History className="size-3" />}>{a.action}</Badge>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-ink-2">{a.entity_id ?? '-'}</td>
                  <td className="max-w-md px-4 py-2.5 font-mono text-[11px] break-words text-ink-3">
                    {Object.keys(a.details).length ? JSON.stringify(a.details).slice(0, 220) : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
