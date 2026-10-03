import { useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowUp, BookOpen, ExternalLink, Loader2, MessageSquarePlus, MessagesSquare, Sparkles, Ticket, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Link, useSearchParams } from 'react-router'
import remarkGfm from 'remark-gfm'
import { toast } from 'sonner'
import { CitationChip, SimilarityBar } from '../components/sources'
import { Drawer, Mono } from '../components/ui'
import { api, request, streamSSE } from '../lib/api'
import { useAuth } from '../lib/auth'
import { dayLabel } from '../lib/format'
import type { ChatMessage, ChatSession, ChatSourceSummary } from '../lib/types'

const SUGGESTIONS = [
  'The customer has a red LOS light on the router. What should I check?',
  'What can I offer a customer asking for compensation after a 3 day outage?',
  'How do I handle a suspected SIM swap?',
  'Channels are missing after a DTH recharge, how do I fix it?',
]

//turn [KB-001] (or a group like [KB-001, TCK-10023]) into links we can render as citation chips
function withCitationLinks(text: string) {
  return text.replace(/\[((?:KB|TCK)-\d+(?:\s*,\s*(?:KB|TCK)-\d+)*)\]/g, (_, group: string) =>
    group
      .split(',')
      .map((ref) => `[${ref.trim()}](#cite-${ref.trim()})`)
      .join(' '),
  )
}

export default function Assistant() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const sessionId = Number(params.get('s')) || null
  const ticketRef = params.get('ticket')
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [busy, setBusy] = useState(false)
  const [source, setSource] = useState<ChatSourceSummary | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const textarea = useRef<HTMLTextAreaElement>(null)

  const sessions = useQuery({ queryKey: ['chat', 'sessions'], queryFn: () => api.get<ChatSession[]>('/v1/chat/sessions') })
  const current = sessions.data?.find((s) => s.id === sessionId)

  //opened from a ticket page: start a chat that knows about that ticket
  useEffect(() => {
    if (!ticketRef) return
    api
      .post<ChatSession>('/v1/chat/sessions', { ticket_ref: ticketRef })
      .then((s) => {
        qc.invalidateQueries({ queryKey: ['chat', 'sessions'] })
        setParams({ s: String(s.id) }, { replace: true })
      })
      .catch((e) => toast.error(e.message))
  }, [ticketRef, qc, setParams])

  useEffect(() => {
    if (!sessionId) {
      setMessages([])
      return
    }
    api.get<ChatMessage[]>(`/v1/chat/sessions/${sessionId}/messages`).then(setMessages).catch(() => setMessages([]))
  }, [sessionId])

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  const send = async (text: string) => {
    const content = text.trim()
    if (!content || busy) return
    setBusy(true)
    setInput('')
    let id = sessionId
    try {
      if (!id) {
        const s = await api.post<ChatSession>('/v1/chat/sessions', {})
        id = s.id
        setParams({ s: String(s.id) }, { replace: true })
      }
      const now = new Date().toISOString()
      setMessages((m) => [
        ...m,
        { id: -1, role: 'user', content, sources: [], created_at: now },
        { id: -2, role: 'assistant', content: '', sources: [], created_at: now, streaming: true },
      ])
      const patchLast = (fn: (m: ChatMessage) => ChatMessage) =>
        setMessages((all) => all.map((m, i) => (i === all.length - 1 ? fn(m) : m)))

      await streamSSE(`/v1/chat/sessions/${id}/messages`, { content }, (event, data) => {
        if (event === 'sources') patchLast((m) => ({ ...m, sources: data as ChatSourceSummary[] }))
        if (event === 'token') patchLast((m) => ({ ...m, content: m.content + (data as string) }))
        if (event === 'done') patchLast((m) => ({ ...m, id: (data as { id: number }).id, streaming: false }))
      })
      qc.invalidateQueries({ queryKey: ['chat', 'sessions'] })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Something went wrong')
      setMessages((m) => m.filter((x) => !x.streaming))
    } finally {
      setBusy(false)
      textarea.current?.focus()
    }
  }

  const remove = async (id: number) => {
    await request(`/v1/chat/sessions/${id}`, { method: 'DELETE' })
    qc.invalidateQueries({ queryKey: ['chat', 'sessions'] })
    if (id === sessionId) setParams({})
  }

  return (
    <div className="flex h-full">
      {/* chat history */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-line md:flex">
        <div className="px-3 pt-16 pb-2">
          <button
            onClick={() => setParams({})}
            className="flex w-full items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm text-ink-2 transition hover:bg-raised hover:text-ink"
          >
            <MessageSquarePlus className="size-4" /> New chat
          </button>
        </div>
        <div className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-3">
          {sessions.data?.map((s, i, all) => (
            <div key={s.id}>
              {(i === 0 || dayLabel(all[i - 1].updated_at) !== dayLabel(s.updated_at)) && (
                <div className="px-2 pt-3 pb-1 text-[11px] font-semibold tracking-wide text-ink-3 uppercase">
                  {dayLabel(s.updated_at)}
                </div>
              )}
              <div
                className={clsx(
                  'group flex items-center gap-2 rounded-lg px-2 py-1.5 text-[13px] transition',
                  s.id === sessionId ? 'bg-raised text-ink' : 'text-ink-2 hover:bg-raised/60',
                )}
              >
                <button onClick={() => setParams({ s: String(s.id) })} className="min-w-0 flex-1 truncate text-left">
                  {s.ticket_ref && <Ticket className="mr-1.5 inline size-3 text-info" />}
                  {s.title}
                </button>
                <button
                  onClick={() => remove(s.id)}
                  className="rounded p-0.5 text-ink-3 opacity-0 transition group-hover:opacity-100 hover:text-danger"
                  title="Delete chat"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* thread */}
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl px-6 pt-16 pb-6">
            {current?.ticket_ref && (
              <div className="mb-6 flex items-center gap-2 rounded-xl border border-info/20 bg-info/5 px-4 py-2.5 text-sm text-ink-2">
                <Ticket className="size-4 text-info" />
                Answers take the complaint in
                <Link to={`/tickets/${current.ticket_ref}`} className="font-mono text-info hover:underline">
                  {current.ticket_ref}
                </Link>
                into account.
              </div>
            )}

            {messages.length === 0 ? (
              <div className="pt-[12vh] text-center">
                <div className="mx-auto mb-5 grid size-12 place-items-center rounded-2xl border border-line bg-gradient-to-b from-raised to-card">
                  <MessagesSquare className="size-5 text-accent" />
                </div>
                <h1 className="text-2xl font-semibold tracking-tight">How can I help, {user?.full_name.split(' ')[0]}?</h1>
                <p className="mt-2 text-sm text-ink-3">
                  Ask about any broadband, mobile, DTH or billing issue. Answers come from the knowledge base and past
                  tickets, with sources.
                </p>
                <div className="mt-8 grid gap-2 text-left sm:grid-cols-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      className="rounded-xl border border-line bg-card px-4 py-3 text-sm text-ink-2 transition hover:border-line-strong hover:text-ink"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-8">
                {messages.map((m, i) =>
                  m.role === 'user' ? (
                    <div key={i} className="flex justify-end">
                      <div className="max-w-[85%] rounded-2xl rounded-br-md bg-raised px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap">
                        {m.content}
                      </div>
                    </div>
                  ) : (
                    <AssistantMessage key={i} message={m} onCite={(ref) => setSource(m.sources.find((s) => s.ref === ref) ?? null)} />
                  ),
                )}
              </div>
            )}
            <div ref={bottom} />
          </div>
        </div>

        <div className="px-6 pb-6">
          <form
            onSubmit={(e) => {
              e.preventDefault()
              send(input)
            }}
            className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border border-line bg-card p-2 shadow-[0_8px_40px_-12px_rgba(0,0,0,0.6)] focus-within:border-line-strong"
          >
            <textarea
              ref={textarea}
              rows={1}
              value={input}
              onChange={(e) => {
                setInput(e.target.value)
                e.target.style.height = 'auto'
                e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send(input)
                }
              }}
              placeholder="Ask the assistant..."
              maxLength={2000}
              className="max-h-[200px] flex-1 resize-none bg-transparent px-3 py-2 text-[15px] text-ink placeholder:text-ink-3 outline-none"
            />
            <button
              type="submit"
              disabled={!input.trim() || busy}
              className="grid size-9 shrink-0 place-items-center rounded-xl bg-accent-strong text-white transition hover:bg-accent disabled:bg-raised disabled:text-ink-3"
            >
              <ArrowUp className="size-4" />
            </button>
          </form>
          <p className="mt-2 text-center text-[11px] text-ink-3">
            The assistant only uses Resolvr's knowledge base and resolved tickets. Check critical cases with an admin.
          </p>
        </div>
      </section>

      <Drawer
        open={!!source}
        onClose={() => setSource(null)}
        title={
          source && (
            <span className="flex items-center gap-2">
              <Mono className="text-ink-2">{source.ref}</Mono> {source.title}
            </span>
          )
        }
      >
        {source && (
          <div className="space-y-4">
            <div className="flex items-center gap-3 text-sm text-ink-3">
              Semantic similarity <SimilarityBar value={source.similarity} />
            </div>
            <p className="text-sm leading-relaxed text-ink-2">{source.snippet}...</p>
            <Link
              to={source.kind === 'kb' ? `/knowledge/${source.ref}` : `/tickets/${source.ref}`}
              className="inline-flex items-center gap-1.5 text-sm text-accent hover:underline"
            >
              Open the full {source.kind === 'kb' ? 'article' : 'ticket'} <ExternalLink className="size-3.5" />
            </Link>
          </div>
        )}
      </Drawer>
    </div>
  )
}

function AssistantMessage({ message: m, onCite }: { message: ChatMessage; onCite: (ref: string) => void }) {
  const [showSources, setShowSources] = useState(false)
  return (
    <div className="flex gap-4">
      <div className="grid size-8 shrink-0 place-items-center rounded-lg border border-line bg-raised">
        <Sparkles className="size-4 text-accent" />
      </div>
      <div className="min-w-0 flex-1">
        {m.streaming && !m.content ? (
          <div className="flex items-center gap-2 pt-1.5 text-sm text-ink-3">
            <Loader2 className="size-3.5 animate-spin" />
            Searching the knowledge base and past tickets
          </div>
        ) : (
          <div className="prose prose-sm prose-invert max-w-none text-[15px] leading-relaxed prose-p:text-ink prose-li:text-ink prose-strong:text-ink prose-headings:text-ink">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children }) =>
                  href?.startsWith('#cite-') ? (
                    <CitationChip refId={href.slice(6)} onClick={() => onCite(href.slice(6))} />
                  ) : (
                    <a href={href} target="_blank" rel="noreferrer">
                      {children}
                    </a>
                  ),
              }}
            >
              {withCitationLinks(m.content)}
            </ReactMarkdown>
          </div>
        )}
        {!m.streaming && m.sources.length > 0 && (
          <div className="mt-3">
            <button onClick={() => setShowSources((s) => !s)} className="flex items-center gap-1.5 text-xs text-ink-3 hover:text-ink-2">
              <BookOpen className="size-3.5" />
              {showSources ? 'Hide' : 'Show'} {m.sources.length} sources searched
            </button>
            {showSources && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {m.sources.map((s) => (
                  <CitationChip key={s.ref} refId={s.ref} onClick={() => onCite(s.ref)} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
