import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, ArrowLeft, BookOpen, FilePlus2, Layers, Pencil, RotateCcw, Search, Tag, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Link, useNavigate, useParams } from 'react-router'
import remarkGfm from 'remark-gfm'
import { toast } from 'sonner'
import { Badge, Button, Card, EmptyState, Mono, PageHeader, Skeleton } from '../components/ui'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { dateTime, titleCase } from '../lib/format'
import type { KbArticle } from '../lib/types'

export function canWriteKb(role?: string) {
  return role === 'admin' || role === 'analyst'
}

export function KnowledgeList() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [q, setQ] = useState('')
  const [product, setProduct] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['kb', user?.role],
    queryFn: () => api.get<KbArticle[]>(`/v1/kb${user?.role === 'admin' ? '?include_archived=true' : ''}`),
  })

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api.post<KbArticle>('/v1/kb/upload', form)
    },
    onSuccess: (a) => {
      toast.success(`${a.ref} published and searchable`)
      qc.invalidateQueries({ queryKey: ['kb'] })
      navigate(`/knowledge/${a.ref}`)
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const term = q.trim().toLowerCase()
  const articles = (data ?? []).filter(
    (a) =>
      (!product || a.product === product) &&
      (!term || `${a.ref} ${a.title} ${a.excerpt} ${a.tags.join(' ')}`.toLowerCase().includes(term)),
  )

  return (
    <div className="mx-auto max-w-6xl px-6 pt-16 pb-16">
      <PageHeader
        title="Knowledge base"
        subtitle="Official troubleshooting guides. New and edited articles are used by the assistant straight away."
        actions={
          canWriteKb(user?.role) && (
            <>
              <input
                ref={fileInput}
                type="file"
                accept=".md,.markdown"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) upload.mutate(f)
                  e.target.value = ''
                }}
              />
              <Button icon={<Upload className="size-4" />} loading={upload.isPending} onClick={() => fileInput.current?.click()}>
                Upload .md
              </Button>
              <Button variant="primary" icon={<FilePlus2 className="size-4" />} onClick={() => navigate('/knowledge/new')}>
                New article
              </Button>
            </>
          )
        }
      />

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
          <input className="input pl-9" placeholder="Search articles" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="flex gap-1">
          {['', 'broadband', 'mobile', 'dth', 'billing'].map((p) => (
            <button
              key={p || 'all'}
              onClick={() => setProduct(p)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                product === p ? 'bg-raised text-ink' : 'text-ink-3 hover:text-ink-2'
              }`}
            >
              {p ? titleCase(p) : 'All'}
            </button>
          ))}
        </div>
        <span className="ml-auto text-xs text-ink-3">{articles.length} articles</span>
      </div>

      {isLoading ? (
        <div className="grid gap-3 md:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      ) : articles.length === 0 ? (
        <Card>
          <EmptyState icon={<BookOpen className="size-5" />} title="No articles found" />
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {articles.map((a) => (
            <Link
              key={a.ref}
              to={`/knowledge/${a.ref}`}
              className="group card flex flex-col p-4 transition hover:border-line-strong hover:bg-raised/40"
            >
              <div className="flex items-center gap-2 text-xs">
                <Mono className="text-ink-3">{a.ref}</Mono>
                {a.category && <Badge>{a.category.name}</Badge>}
                {a.status === 'archived' && <Badge tone="warn">Archived</Badge>}
              </div>
              <h3 className="mt-2.5 font-medium text-ink group-hover:text-white">{a.title}</h3>
              <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-ink-3">{a.excerpt}</p>
              <div className="mt-auto flex items-center justify-between pt-3 text-[11px] text-ink-3">
                <span>{titleCase(a.product) || 'All products'}</span>
                <span>
                  v{a.version} · updated {dateTime(a.updated_at)}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

export function KnowledgeArticle() {
  const { ref } = useParams()
  const { user } = useAuth()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { data: a, isLoading, error } = useQuery({
    queryKey: ['kb', 'article', ref],
    queryFn: () => api.get<KbArticle>(`/v1/kb/${ref}`),
  })

  const toggleArchive = useMutation({
    mutationFn: () => api.post<KbArticle>(`/v1/kb/${ref}/${a?.status === 'archived' ? 'restore' : 'archive'}`),
    onSuccess: (updated) => {
      qc.setQueryData(['kb', 'article', ref], updated)
      qc.invalidateQueries({ queryKey: ['kb'] })
      toast.success(updated.status === 'archived' ? 'Archived, no longer used for answers' : 'Restored')
    },
  })

  if (isLoading) return <Skeleton className="mx-auto mt-16 h-96 max-w-4xl" />
  if (error || !a) return <EmptyState icon={<BookOpen className="size-5" />} title="Article not found" />

  return (
    <div className="mx-auto max-w-6xl px-6 pt-16 pb-16">
      <button onClick={() => navigate('/knowledge')} className="mb-4 flex items-center gap-1.5 text-sm text-ink-3 hover:text-ink">
        <ArrowLeft className="size-4" /> Knowledge base
      </button>
      <div className="grid gap-8 lg:grid-cols-[1fr_260px]">
        <article className="min-w-0">
          <div className="flex items-center gap-2 text-xs">
            <Mono className="text-ink-3">{a.ref}</Mono>
            {a.status === 'archived' && <Badge tone="warn">Archived</Badge>}
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">{a.title}</h1>
          <div className="prose prose-invert mt-6 max-w-none prose-headings:font-semibold prose-headings:tracking-tight prose-headings:text-ink prose-h2:mt-8 prose-h2:border-b prose-h2:border-line prose-h2:pb-2 prose-h2:text-lg prose-p:text-ink-2 prose-a:text-accent prose-strong:text-ink prose-code:rounded prose-code:bg-raised prose-code:px-1 prose-code:py-0.5 prose-code:text-ink prose-code:before:content-none prose-code:after:content-none prose-li:text-ink-2 prose-li:marker:text-ink-3">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{a.content_md ?? ''}</ReactMarkdown>
          </div>
        </article>

        <aside className="space-y-4">
          {canWriteKb(user?.role) && (
            <div className="flex gap-2">
              <Button className="flex-1" icon={<Pencil className="size-4" />} onClick={() => navigate(`/knowledge/${a.ref}/edit`)}>
                Edit
              </Button>
              {user?.role === 'admin' && (
                <Button
                  icon={a.status === 'archived' ? <RotateCcw className="size-4" /> : <Archive className="size-4" />}
                  loading={toggleArchive.isPending}
                  onClick={() => toggleArchive.mutate()}
                  title={a.status === 'archived' ? 'Restore' : 'Archive'}
                />
              )}
            </div>
          )}
          <Card className="divide-y divide-line text-sm">
            {[
              ['Category', a.category?.name ?? '-'],
              ['Product', titleCase(a.product) || 'All'],
              ['Version', `v${a.version}`],
              ['Updated', dateTime(a.updated_at)],
              ['Author', a.author ?? '-'],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 px-4 py-2.5">
                <span className="text-ink-3">{k}</span>
                <span className="text-right text-ink-2">{v}</span>
              </div>
            ))}
            <div className="flex items-center gap-2 px-4 py-2.5 text-xs text-ink-3">
              <Layers className="size-3.5" /> Indexed as {a.chunks} searchable sections
            </div>
          </Card>
          {a.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {a.tags.map((t) => (
                <Badge key={t} icon={<Tag className="size-3" />}>
                  {t}
                </Badge>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
