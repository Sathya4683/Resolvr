import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { Download, FileSpreadsheet, FileUp, Loader2, UploadCloud } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { Link, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { ReviewBadge, SeverityIcon } from '../components/badges'
import { Badge, Button, Card, CardHeader, EmptyState, Mono, PageHeader } from '../components/ui'
import { api, downloadFile } from '../lib/api'
import { dateTime, titleCase } from '../lib/format'
import type { BatchJob } from '../lib/types'

const TEMPLATE = `complaint,subject,customer_ref,channel,product_hint
"Internet drops every evening around 8, already restarted the router",Evening drops,CUST-100001,phone,broadband
"Recharged DTH but channels still not showing",Channels missing,CUST-100002,app,dth
`

function downloadTemplate() {
  const url = URL.createObjectURL(new Blob([TEMPLATE], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = 'complaints-template.csv'
  a.click()
  URL.revokeObjectURL(url)
}

export default function Batch() {
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const jobs = useQuery({
    queryKey: ['batch'],
    queryFn: () => api.get<BatchJob[]>('/v1/batch'),
    refetchInterval: (q) => (q.state.data?.some((j) => j.status === 'queued' || j.status === 'running') ? 2000 : false),
  })
  const selectedId = Number(params.get('job')) || jobs.data?.[0]?.id
  const selected = jobs.data?.find((j) => j.id === selectedId)

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api.post<BatchJob>('/v1/batch', form)
    },
    onSuccess: (job) => {
      toast.success(`Queued ${job.total} complaints`)
      qc.invalidateQueries({ queryKey: ['batch'] })
      setParams({ job: String(job.id) })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) upload.mutate(file)
  }

  return (
    <div className="mx-auto max-w-6xl px-6 pt-16 pb-16">
      <PageHeader
        title="Batch upload"
        subtitle="Upload a CSV of new complaints. Each row is analysed in the background and you can download the results when it's done."
        actions={
          <Button icon={<Download className="size-4" />} onClick={downloadTemplate}>
            CSV template
          </Button>
        }
      />

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => input.current?.click()}
        className={clsx(
          'flex cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed px-6 py-12 text-center transition',
          dragging ? 'border-accent bg-accent/5' : 'border-line-strong bg-card hover:border-ink-3',
        )}
      >
        <input
          ref={input}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) upload.mutate(file)
            e.target.value = ''
          }}
        />
        {upload.isPending ? (
          <Loader2 className="size-7 animate-spin text-accent" />
        ) : (
          <UploadCloud className="size-7 text-ink-3" />
        )}
        <p className="mt-3 text-sm font-medium">{upload.isPending ? 'Uploading...' : 'Drop a CSV here or click to browse'}</p>
        <p className="mt-1 text-xs text-ink-3">
          Required column <Mono>complaint</Mono>. Optional <Mono>subject</Mono>, <Mono>customer_ref</Mono>,{' '}
          <Mono>channel</Mono>, <Mono>product_hint</Mono>. Up to 200 rows, 2 MB.
        </p>
      </div>

      <div className="mt-8 grid gap-5 lg:grid-cols-[280px_1fr]">
        <div className="space-y-2">
          <h3 className="px-1 text-xs font-semibold tracking-wide text-ink-3 uppercase">Recent jobs</h3>
          {!jobs.data?.length && <p className="px-1 text-sm text-ink-3">No uploads yet</p>}
          {jobs.data?.map((job) => (
            <button
              key={job.id}
              onClick={() => setParams({ job: String(job.id) })}
              className={clsx(
                'w-full rounded-xl border p-3 text-left transition',
                job.id === selectedId ? 'border-accent/50 bg-accent/[0.06]' : 'border-line bg-card hover:border-line-strong',
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="flex min-w-0 items-center gap-2 text-sm font-medium">
                  <FileSpreadsheet className="size-4 shrink-0 text-ink-3" />
                  <span className="truncate">{job.filename ?? `Job #${job.id}`}</span>
                </span>
                <JobStatus job={job} />
              </div>
              <Progress job={job} />
              <div className="mt-1.5 text-[11px] text-ink-3">{dateTime(job.created_at)}</div>
            </button>
          ))}
        </div>

        {selected ? (
          <Card className="min-w-0">
            <CardHeader
              title={`Job #${selected.id} · ${selected.filename ?? 'upload'}`}
              subtitle={`${selected.processed} of ${selected.total} processed${selected.failed ? ` · ${selected.failed} failed` : ''}`}
              icon={<FileUp className="size-4" />}
              action={
                <Button
                  size="sm"
                  icon={<Download className="size-3.5" />}
                  disabled={selected.status !== 'done'}
                  onClick={() => downloadFile(`/v1/batch/${selected.id}/results.csv`, `batch-${selected.id}-results.csv`)}
                >
                  Results CSV
                </Button>
              }
            />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-line bg-panel text-left text-xs text-ink-3">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">Row</th>
                    <th className="px-4 py-2.5 font-medium">Ticket</th>
                    <th className="px-4 py-2.5 font-medium">Category</th>
                    <th className="px-4 py-2.5 font-medium">Severity</th>
                    <th className="px-4 py-2.5 font-medium">Review</th>
                    <th className="px-4 py-2.5 font-medium">Top source</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {selected.results.map((r) => (
                    <tr key={r.row} className="hover:bg-raised/40">
                      <td className="px-4 py-2.5 text-ink-3 tabular-nums">{r.row}</td>
                      {r.error ? (
                        <td colSpan={5} className="px-4 py-2.5 text-xs text-danger">
                          {r.error}
                        </td>
                      ) : (
                        <>
                          <td className="px-4 py-2.5">
                            <Link to={`/tickets/${r.ticket_ref}`} className="font-mono text-xs text-accent hover:underline">
                              {r.ticket_ref}
                            </Link>
                          </td>
                          <td className="px-4 py-2.5 text-ink-2">{titleCase(r.category) || '-'}</td>
                          <td className="px-4 py-2.5">
                            <span className="flex items-center gap-2 text-ink-2">
                              <SeverityIcon severity={r.severity ?? null} />
                              {titleCase(r.severity)}
                            </span>
                          </td>
                          <td className="px-4 py-2.5">{r.review_status && <ReviewBadge status={r.review_status} />}</td>
                          <td className="px-4 py-2.5 font-mono text-xs text-ink-3">{r.top_source ?? '-'}</td>
                        </>
                      )}
                    </tr>
                  ))}
                  {selected.processed < selected.total &&
                    Array.from({ length: Math.min(3, selected.total - selected.processed) }).map((_, i) => (
                      <tr key={`pending-${i}`}>
                        <td className="px-4 py-2.5 text-ink-3 tabular-nums">{selected.processed + i + 1}</td>
                        <td colSpan={5} className="px-4 py-2.5 text-xs text-ink-3">
                          {i === 0 && selected.status === 'running' ? 'Analysing...' : 'Waiting'}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </Card>
        ) : (
          <Card>
            <EmptyState
              icon={<FileSpreadsheet className="size-5" />}
              title="Upload a CSV to get started"
              text="Complaints are analysed one by one. Critical ones still go to an admin before the draft is visible."
            />
          </Card>
        )}
      </div>
    </div>
  )
}

function JobStatus({ job }: { job: BatchJob }) {
  if (job.status === 'done') return <Badge tone="ok">Done</Badge>
  if (job.status === 'failed') return <Badge tone="danger">Failed</Badge>
  if (job.status === 'running') return <Badge tone="accent">Running</Badge>
  return <Badge>Queued</Badge>
}

function Progress({ job }: { job: BatchJob }) {
  const pct = job.total ? (job.processed / job.total) * 100 : 0
  return (
    <div className="mt-2.5 h-1 overflow-hidden rounded-full bg-raised">
      <div
        className={clsx('h-full rounded-full transition-all duration-500', job.status === 'done' ? 'bg-ok' : 'bg-accent')}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}
