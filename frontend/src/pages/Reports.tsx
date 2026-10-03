import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { CalendarDays, Download, FileBarChart2, Mail, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Badge, Button, Card, CardHeader, PageHeader } from '../components/ui'
import { api, downloadFile } from '../lib/api'
import { useAuth } from '../lib/auth'
import { dateTime } from '../lib/format'

interface DigestRun {
  id: number
  report_date: string
  trigger: 'cron' | 'manual'
  status: 'sending' | 'sent' | 'failed'
  attempts: number
  recipients: string[]
  error: string | null
  created_at: string
  sent_at: string | null
}

function isoToday() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
}

function dayChip(iso: string) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })
}

export default function Reports() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const qc = useQueryClient()
  const [day, setDay] = useState(isoToday())
  const [start, setStart] = useState('2026-10-01')
  const [end, setEnd] = useState(isoToday())
  const [downloading, setDownloading] = useState<string | null>(null)

  const days = useQuery({ queryKey: ['reports', 'days'], queryFn: () => api.get<{ day: string; tickets: number }[]>('/v1/reports/days') })
  const runs = useQuery({ queryKey: ['reports', 'runs'], queryFn: () => api.get<DigestRun[]>('/v1/reports/digests'), enabled: isAdmin })

  const sendNow = useMutation({
    mutationFn: () => api.post<{ recipients: string[] }>(`/v1/reports/digest/send?date=${day}`),
    onSuccess: (r) => {
      toast.success(`Digest emailed to ${r.recipients.length} admin${r.recipients.length === 1 ? '' : 's'}`)
      qc.invalidateQueries({ queryKey: ['reports', 'runs'] })
    },
    onError: (e: Error) => {
      toast.error(e.message)
      qc.invalidateQueries({ queryKey: ['reports', 'runs'] })
    },
  })

  const download = async (path: string, name: string, key: string) => {
    setDownloading(key)
    try {
      await downloadFile(path, name)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Download failed')
    } finally {
      setDownloading(null)
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-6 pt-16 pb-16">
      <PageHeader title="Reports" subtitle="PDF reports for audits and evaluation, generated from live data at download time." />

      {isAdmin && (
        <Card className="mb-5">
          <CardHeader
            title="Daily digest"
            subtitle="Everything that happened on the desk in one day. Emailed to the admin list every evening at 9 PM IST."
            icon={<FileBarChart2 className="size-4" />}
          />
          <div className="p-5">
            <div className="label">Day</div>
            <div className="flex flex-wrap gap-2">
              {(days.data ?? []).slice(0, 7).map((d) => (
                <button
                  key={d.day}
                  onClick={() => setDay(d.day)}
                  className={clsx(
                    'rounded-lg border px-3 py-2 text-left transition',
                    day === d.day ? 'border-accent/50 bg-accent/10' : 'border-line hover:border-line-strong',
                  )}
                >
                  <div className="text-sm font-medium">{d.day === isoToday() ? 'Today' : dayChip(d.day)}</div>
                  <div className="text-[11px] text-ink-3">{d.tickets} tickets</div>
                </button>
              ))}
              <label className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-ink-2">
                <CalendarDays className="size-4 text-ink-3" />
                <input
                  type="date"
                  value={day}
                  max={isoToday()}
                  onChange={(e) => e.target.value && setDay(e.target.value)}
                  className="bg-transparent text-sm outline-none [color-scheme:dark]"
                />
              </label>
            </div>
            {day === isoToday() && <p className="mt-2 text-xs text-ink-3">Today's report covers everything up to now.</p>}
            <div className="mt-5 flex flex-wrap gap-2">
              <Button
                variant="primary"
                icon={<Download className="size-4" />}
                loading={downloading === 'digest'}
                onClick={() => download(`/v1/reports/digest.pdf?date=${day}`, `resolvr-digest-${day}.pdf`, 'digest')}
              >
                Download PDF
              </Button>
              <Button icon={<Mail className="size-4" />} loading={sendNow.isPending} onClick={() => sendNow.mutate()}>
                Email to admins now
              </Button>
            </div>
          </div>
          {!!runs.data?.length && (
            <div className="border-t border-line">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-ink-3">
                  <tr>
                    <th className="px-5 py-2.5 font-medium">Report day</th>
                    <th className="px-5 py-2.5 font-medium">Trigger</th>
                    <th className="px-5 py-2.5 font-medium">Status</th>
                    <th className="px-5 py-2.5 font-medium">Recipients</th>
                    <th className="px-5 py-2.5 font-medium">Sent</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {runs.data.map((r) => (
                    <tr key={r.id}>
                      <td className="px-5 py-2.5">{dayChip(r.report_date)}</td>
                      <td className="px-5 py-2.5 text-ink-2">{r.trigger === 'cron' ? 'Scheduled' : 'Manual'}</td>
                      <td className="px-5 py-2.5">
                        <Badge tone={r.status === 'sent' ? 'ok' : r.status === 'failed' ? 'danger' : 'neutral'} title={r.error ?? undefined}>
                          {r.status}
                        </Badge>
                      </td>
                      <td className="px-5 py-2.5 text-xs text-ink-3">{r.recipients.join(', ') || '-'}</td>
                      <td className="px-5 py-2.5 text-xs text-ink-3">{r.sent_at ? dateTime(r.sent_at) : r.error ?? '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      <Card>
        <CardHeader
          title="Quality and evaluation report"
          subtitle="Analyst verdicts, rubric pass rates, label agreement, citation quality and accuracy per category."
          icon={<ShieldCheck className="size-4" />}
        />
        <div className="flex flex-wrap items-end gap-3 p-5">
          <div>
            <label className="label">From</label>
            <input type="date" className="input [color-scheme:dark]" value={start} max={end} onChange={(e) => setStart(e.target.value)} />
          </div>
          <div>
            <label className="label">To</label>
            <input type="date" className="input [color-scheme:dark]" value={end} max={isoToday()} onChange={(e) => setEnd(e.target.value)} />
          </div>
          <Button
            variant="primary"
            icon={<Download className="size-4" />}
            loading={downloading === 'quality'}
            onClick={() =>
              download(`/v1/reports/quality.pdf?start=${start}&end=${end}`, `resolvr-quality-${start}-to-${end}.pdf`, 'quality')
            }
          >
            Download PDF
          </Button>
        </div>
      </Card>
    </div>
  )
}
