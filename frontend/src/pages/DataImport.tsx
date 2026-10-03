import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { DatabaseZap, FileSpreadsheet, Loader2, Sparkles, ThumbsDown, ThumbsUp, UploadCloud } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { SeverityIcon } from '../components/badges'
import { Badge, Button, Card, CardHeader, EmptyState, Mono, PageHeader } from '../components/ui'
import { api } from '../lib/api'
import { dateTime, titleCase } from '../lib/format'
import type { Severity } from '../lib/types'

interface ImportReport {
  inserted: number
  updated: number
  duplicates: number
  errors: { row: number; error: string }[]
}

interface Promotable {
  ref: string
  subject: string | null
  snippet: string
  category: string | null
  severity: Severity | null
  resolved_at: string | null
  resolved_by: string | null
  steps: string[]
  feedback: string | null
  analyst_verdict: string | null
}

function ImportCard({ title, help, endpoint, columns }: { title: string; help: string; endpoint: string; columns: string }) {
  const input = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()
  const [report, setReport] = useState<ImportReport | null>(null)
  const run = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api.post<ImportReport>(endpoint, form)
    },
    onSuccess: (r) => {
      setReport(r)
      qc.invalidateQueries()
      toast.success(`Imported ${r.inserted} new${r.updated ? `, updated ${r.updated}` : ''}`)
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <Card>
      <CardHeader title={title} subtitle={help} icon={<FileSpreadsheet className="size-4" />} />
      <div className="p-4">
        <button
          onClick={() => input.current?.click()}
          className="flex w-full flex-col items-center rounded-xl border border-dashed border-line-strong px-4 py-8 text-center transition hover:border-ink-3"
        >
          {run.isPending ? <Loader2 className="size-6 animate-spin text-accent" /> : <UploadCloud className="size-6 text-ink-3" />}
          <span className="mt-2 text-sm">{run.isPending ? 'Importing and embedding...' : 'Choose a CSV file'}</span>
          <span className="mt-1 font-mono text-[11px] text-ink-3">{columns}</span>
        </button>
        <input
          ref={input}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) run.mutate(f)
            e.target.value = ''
          }}
        />
        {report && (
          <div className="mt-4 rounded-lg border border-line bg-panel p-3 text-sm">
            <div className="flex flex-wrap gap-2">
              <Badge tone="ok">{report.inserted} inserted</Badge>
              {report.updated > 0 && <Badge tone="accent">{report.updated} updated</Badge>}
              <Badge>{report.duplicates} duplicates skipped</Badge>
              <Badge tone={report.errors.length ? 'danger' : 'neutral'}>{report.errors.length} rejected</Badge>
            </div>
            {report.errors.length > 0 && (
              <ul className="mt-3 max-h-40 space-y-1 overflow-y-auto text-xs text-ink-3">
                {report.errors.map((e) => (
                  <li key={e.row}>
                    Row {e.row}: <span className="text-danger">{e.error}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}

export default function DataImport() {
  const qc = useQueryClient()
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const promotable = useQuery({
    queryKey: ['promotable'],
    queryFn: () => api.get<Promotable[]>('/v1/data/tickets/promotable'),
  })
  const promote = useMutation({
    mutationFn: () => api.post<{ promoted: string[]; skipped: string[] }>('/v1/data/tickets/promote', { refs: [...picked] }),
    onSuccess: (r) => {
      toast.success(`${r.promoted.length} tickets added to the knowledge pool`)
      setPicked(new Set())
      qc.invalidateQueries({ queryKey: ['promotable'] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const rows = promotable.data ?? []
  return (
    <div className="mx-auto max-w-6xl px-6 pt-16 pb-16">
      <PageHeader
        title="Data & imports"
        subtitle="Grow the knowledge the assistant searches. Imports are idempotent: re-uploading the same file never creates duplicates."
      />
      <div className="grid gap-5 md:grid-cols-2">
        <ImportCard
          title="Resolved tickets"
          help="Historical tickets with their resolution steps"
          endpoint="/v1/data/tickets/import"
          columns="complaint, category, severity, resolution_steps (| separated) + optional fields"
        />
        <ImportCard
          title="Knowledge articles"
          help="Markdown articles in bulk (or upload single .md files from the knowledge base)"
          endpoint="/v1/data/kb/import"
          columns="title, content_md, optional ref, product, category, tags"
        />
      </div>

      <Card className="mt-5">
        <CardHeader
          title="Tickets resolved in Resolvr"
          subtitle="Agent-resolved tickets only become searchable after an admin adds them, so wrong fixes never leak into answers."
          icon={<DatabaseZap className="size-4" />}
          action={
            <Button
              variant="primary"
              size="sm"
              icon={<Sparkles className="size-3.5" />}
              disabled={!picked.size}
              loading={promote.isPending}
              onClick={() => promote.mutate()}
            >
              Add {picked.size || ''} to knowledge
            </Button>
          }
        />
        {rows.length === 0 ? (
          <EmptyState
            icon={<DatabaseZap className="size-5" />}
            title="Nothing to review"
            text="When agents mark tickets as resolved they'll show up here."
          />
        ) : (
          <div className="divide-y divide-line">
            {rows.map((t) => (
              <label key={t.ref} className={clsx('flex cursor-pointer gap-3 px-5 py-3.5 transition', picked.has(t.ref) ? 'bg-accent/5' : 'hover:bg-raised/40')}>
                <input
                  type="checkbox"
                  className="mt-1 accent-[#6366f1]"
                  checked={picked.has(t.ref)}
                  onChange={() => {
                    const next = new Set(picked)
                    if (next.has(t.ref)) next.delete(t.ref)
                    else next.add(t.ref)
                    setPicked(next)
                  }}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-ink-3">
                    <SeverityIcon severity={t.severity} />
                    <Link to={`/tickets/${t.ref}`} className="font-mono text-accent hover:underline" onClick={(e) => e.stopPropagation()}>
                      {t.ref}
                    </Link>
                    <span>{t.category ?? 'uncategorised'}</span>
                    <span>· resolved by {t.resolved_by ?? '-'}</span>
                    {t.resolved_at && <span>· {dateTime(t.resolved_at)}</span>}
                    {t.feedback === 'up' && <Badge tone="ok" icon={<ThumbsUp className="size-3" />}>agent liked the draft</Badge>}
                    {t.feedback === 'down' && <Badge tone="danger" icon={<ThumbsDown className="size-3" />}>agent disliked the draft</Badge>}
                    {t.analyst_verdict && <Badge tone={t.analyst_verdict === 'correct' ? 'ok' : 'warn'}>analyst: {titleCase(t.analyst_verdict)}</Badge>}
                  </div>
                  <div className="mt-1 text-sm text-ink-2">{t.subject || t.snippet}</div>
                  <ol className="mt-1.5 list-decimal space-y-0.5 pl-5 text-xs text-ink-3">
                    {t.steps.slice(0, 4).map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ol>
                </div>
              </label>
            ))}
          </div>
        )}
      </Card>
      <p className="mt-3 text-xs text-ink-3">
        <Mono>Tip:</Mono> the analyst verdict and agent feedback help decide which resolutions are good enough to reuse.
      </p>
    </div>
  )
}
