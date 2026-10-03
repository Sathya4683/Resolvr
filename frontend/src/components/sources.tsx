import clsx from 'clsx'
import { BookOpen, ExternalLink, Ticket } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { Link } from 'react-router'
import remarkGfm from 'remark-gfm'
import type { Source } from '../lib/types'
import { Badge, Drawer, Mono } from './ui'

export function CitationChip({ refId, onClick }: { refId: string; onClick?: () => void }) {
  const kb = refId.startsWith('KB-')
  return (
    <button
      onClick={onClick}
      className={clsx(
        'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 font-mono text-[11px] transition',
        kb
          ? 'border-accent/25 bg-accent/10 text-accent hover:bg-accent/20'
          : 'border-info/25 bg-info/10 text-info hover:bg-info/20',
      )}
    >
      {kb ? <BookOpen className="size-3" /> : <Ticket className="size-3" />}
      {refId}
    </button>
  )
}

export function SimilarityBar({ value, compact }: { value: number; compact?: boolean }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div className="flex shrink-0 items-center gap-2">
      <div className={clsx('h-1.5 overflow-hidden rounded-full bg-raised', compact ? 'w-10' : 'w-20')}>
        <div
          className={clsx('h-full rounded-full', pct >= 75 ? 'bg-ok' : pct >= 60 ? 'bg-accent' : 'bg-ink-3')}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-ink-2 tabular-nums">{Math.round(pct)}%</span>
    </div>
  )
}

export function SourceCard({ source, onOpen, cited }: { source: Source; onOpen: () => void; cited?: boolean }) {
  const kb = source.kind === 'kb'
  return (
    <button
      onClick={onOpen}
      className="group flex w-full flex-col gap-2 rounded-xl border border-line bg-panel p-3.5 text-left transition hover:border-line-strong hover:bg-raised/50"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className={clsx(
              'grid size-6 shrink-0 place-items-center rounded-md',
              kb ? 'bg-accent/10 text-accent' : 'bg-info/10 text-info',
            )}
          >
            {kb ? <BookOpen className="size-3.5" /> : <Ticket className="size-3.5" />}
          </span>
          <Mono className="whitespace-nowrap text-ink-2">{source.ref}</Mono>
          {cited && <Badge tone="ok">cited</Badge>}
        </div>
        <SimilarityBar value={source.similarity} compact />
      </div>
      <div className="line-clamp-1 text-sm font-medium text-ink group-hover:text-white">{source.title}</div>
      <div className="line-clamp-2 text-xs leading-relaxed text-ink-3">{source.snippet}</div>
    </button>
  )
}

export function SourceDrawer({ source, onClose }: { source: Source | null; onClose: () => void }) {
  return (
    <Drawer
      open={!!source}
      onClose={onClose}
      title={
        source && (
          <div className="flex items-center gap-2">
            <Mono className="text-ink-2">{source.ref}</Mono>
            <span className="truncate">{source.title}</span>
          </div>
        )
      }
    >
      {source && (
        <div className="space-y-5">
          <div className="rounded-xl border border-line bg-card p-4">
            <div className="mb-3 text-xs font-semibold tracking-wide text-ink-3 uppercase">Why this matched</div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="text-xs text-ink-3">Semantic similarity</div>
                <SimilarityBar value={source.similarity} />
              </div>
              <div>
                <div className="text-xs text-ink-3">Reranker relevance</div>
                {source.rerank_score !== null ? <SimilarityBar value={source.rerank_score} /> : <span>-</span>}
              </div>
              <div>
                <div className="text-xs text-ink-3">Vector rank</div>
                <div className="tabular-nums">{source.vector_rank ? `#${source.vector_rank}` : 'not in top list'}</div>
              </div>
              <div>
                <div className="text-xs text-ink-3">Keyword rank</div>
                <div className="tabular-nums">{source.keyword_rank ? `#${source.keyword_rank}` : 'not in top list'}</div>
              </div>
            </div>
            {source.matched_terms.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {source.matched_terms.map((t) => (
                  <Badge key={t}>{t}</Badge>
                ))}
              </div>
            )}
          </div>

          <div className="prose prose-sm prose-invert max-w-none prose-headings:text-ink prose-p:text-ink-2 prose-li:text-ink-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {source.kind === 'kb' ? source.content : source.content.replace(/\n/g, '\n\n')}
            </ReactMarkdown>
          </div>

          <Link
            to={source.kind === 'kb' ? `/knowledge/${source.ref}` : `/tickets/${source.ref}`}
            className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline"
          >
            Open {source.kind === 'kb' ? 'article' : 'ticket'} <ExternalLink className="size-3.5" />
          </Link>
        </div>
      )}
    </Drawer>
  )
}
