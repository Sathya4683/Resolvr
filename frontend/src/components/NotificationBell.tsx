import { useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Bell, CheckCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { api } from '../lib/api'
import { timeAgo } from '../lib/format'

interface Notification {
  id: number
  kind: string
  title: string
  body: string | null
  link: string | null
  is_read: boolean
  created_at: string
}

export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const qc = useQueryClient()
  const seen = useRef<Set<number> | null>(null)

  const { data = [], isSuccess } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => api.get<Notification[]>('/v1/notifications'),
    refetchInterval: 15_000,
  })
  const unread = data.filter((n) => !n.is_read).length

  //pop a toast for anything new that arrived since the last poll (not for what was already there on page load)
  useEffect(() => {
    if (!isSuccess) return
    if (seen.current === null) {
      seen.current = new Set(data.map((n) => n.id))
      return
    }
    for (const n of data.slice(0, 3)) {
      if (!seen.current.has(n.id) && !n.is_read) {
        toast(n.title, {
          description: n.body ?? undefined,
          action: n.link ? { label: 'Open', onClick: () => navigate(n.link!) } : undefined,
        })
        //the sidebar status dots should update too
        qc.invalidateQueries({ queryKey: ['tickets'] })
      }
      seen.current.add(n.id)
    }
  }, [data, isSuccess, navigate, qc])

  const markAll = async () => {
    await api.post('/v1/notifications/read-all')
    qc.invalidateQueries({ queryKey: ['notifications'] })
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative rounded-lg border border-line bg-panel/80 p-2 text-ink-2 backdrop-blur transition hover:text-ink"
      >
        <Bell className="size-4" />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 grid min-w-4 place-items-center rounded-full bg-accent-strong px-1 text-[10px] font-semibold text-white">
            {unread}
          </span>
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-40 mt-2 w-96 overflow-hidden rounded-xl border border-line bg-card shadow-2xl">
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <span className="text-sm font-semibold">Notifications</span>
              {unread > 0 && (
                <button onClick={markAll} className="flex items-center gap-1 text-xs text-ink-3 hover:text-ink">
                  <CheckCheck className="size-3.5" /> Mark all read
                </button>
              )}
            </div>
            <div className="max-h-96 overflow-y-auto">
              {data.length === 0 && <p className="px-4 py-8 text-center text-sm text-ink-3">You're all caught up</p>}
              {data.map((n) => (
                <button
                  key={n.id}
                  onClick={async () => {
                    setOpen(false)
                    if (!n.is_read) await api.post(`/v1/notifications/${n.id}/read`).catch(() => {})
                    qc.invalidateQueries({ queryKey: ['notifications'] })
                    if (n.link) navigate(n.link)
                  }}
                  className={clsx(
                    'flex w-full gap-3 border-b border-line/60 px-4 py-3 text-left transition hover:bg-raised',
                    !n.is_read && 'bg-accent/[0.06]',
                  )}
                >
                  <div className="min-w-0">
                    <div className={clsx('text-sm', n.is_read ? 'text-ink-2' : 'font-medium text-ink')}>{n.title}</div>
                    {n.body && <div className="mt-0.5 line-clamp-2 text-xs text-ink-3">{n.body}</div>}
                    <div className="mt-1 text-[11px] text-ink-3">{timeAgo(n.created_at)}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
