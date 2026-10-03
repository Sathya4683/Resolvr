import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import MDEditor from '@uiw/react-md-editor'
import { ArrowLeft, FileDown, Plus, Save } from 'lucide-react'
import { useEffect, useState, type DragEvent } from 'react'
import { useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { Button, Card, PageHeader } from '../components/ui'
import { api } from '../lib/api'
import type { Category, KbArticle } from '../lib/types'
import { CategoryForm } from './Categories'

const STARTER = `## Symptoms
- What the customer notices

## Likely causes
- Why it usually happens

## Steps
1. First thing the agent should do
2. Next step

## Escalate when
- When to hand it over to a specialist team
`

//reads the optional front matter block of a dropped .md file (title, category, product, tags)
function parseFrontMatter(text: string) {
  const match = text.match(/^---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)$/)
  if (!match) return { meta: {} as Record<string, string>, body: text }
  const meta: Record<string, string> = {}
  for (const line of match[1].split('\n')) {
    const i = line.indexOf(':')
    if (i > 0) meta[line.slice(0, i).trim().toLowerCase()] = line.slice(i + 1).trim()
  }
  return { meta, body: match[2] }
}

export default function KnowledgeEditor() {
  const { ref } = useParams()
  const editing = Boolean(ref)
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [title, setTitle] = useState('')
  const [content, setContent] = useState(STARTER)
  const [category, setCategory] = useState('')
  const [product, setProduct] = useState('')
  const [tags, setTags] = useState('')
  const [dragging, setDragging] = useState(false)
  const [addingCategory, setAddingCategory] = useState(false)

  const categories = useQuery({ queryKey: ['categories'], queryFn: () => api.get<Category[]>('/v1/categories') })
  const existing = useQuery({
    queryKey: ['kb', 'article', ref],
    queryFn: () => api.get<KbArticle>(`/v1/kb/${ref}`),
    enabled: editing,
  })

  useEffect(() => {
    const a = existing.data
    if (!a) return
    setTitle(a.title)
    setContent(a.content_md ?? '')
    setCategory(a.category?.slug ?? '')
    setProduct(a.product ?? '')
    setTags(a.tags.join(', '))
  }, [existing.data])

  const save = useMutation({
    mutationFn: () => {
      const body = {
        title: title.trim(),
        content_md: content,
        category_slug: category || null,
        product: product || null,
        tags: tags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
      }
      return editing ? api.put<KbArticle>(`/v1/kb/${ref}`, body) : api.post<KbArticle>('/v1/kb', body)
    },
    onSuccess: (a) => {
      toast.success(`${a.ref} saved, ${a.chunks} sections indexed for search`)
      qc.invalidateQueries({ queryKey: ['kb'] })
      navigate(`/knowledge/${a.ref}`)
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const loadFile = async (file: File) => {
    if (!/\.(md|markdown)$/i.test(file.name)) {
      toast.error('Drop a .md file')
      return
    }
    const { meta, body } = parseFrontMatter(await file.text())
    let text = body.trim()
    let fileTitle = meta.title
    if (!fileTitle) {
      const heading = text.match(/^#\s+(.+)$/m)
      fileTitle = heading?.[1] ?? file.name.replace(/\.(md|markdown)$/i, '')
      if (heading) text = text.replace(/^#\s+.+\n?/m, '').trim()
    }
    setTitle(fileTitle)
    setContent(text)
    if (meta.category) setCategory(meta.category)
    if (meta.product) setProduct(meta.product)
    if (meta.tags) setTags(meta.tags)
    toast.success(`Loaded ${file.name}, review it and save`)
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) loadFile(file)
  }

  return (
    <div className="mx-auto max-w-7xl px-6 pt-16 pb-16">
      <button
        onClick={() => navigate(editing ? `/knowledge/${ref}` : '/knowledge')}
        className="mb-4 flex items-center gap-1.5 text-sm text-ink-3 hover:text-ink"
      >
        <ArrowLeft className="size-4" /> Back
      </button>
      <PageHeader
        title={editing ? `Edit ${ref}` : 'New article'}
        subtitle="Write in markdown or drop a .md file onto the editor. Saving re-indexes the article for semantic search."
        actions={
          <Button
            variant="primary"
            icon={<Save className="size-4" />}
            loading={save.isPending}
            disabled={title.trim().length < 3 || content.trim().length < 20}
            onClick={() => save.mutate()}
          >
            {editing ? 'Save changes' : 'Publish'}
          </Button>
        }
      />

      <Card className="mb-4 grid gap-4 p-4 md:grid-cols-[2fr_1fr_1fr]">
        <div>
          <label className="label">Title</label>
          <input
            className="input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Router keeps rebooting after a power cut"
            maxLength={200}
          />
        </div>
        <div>
          <div className="flex items-center justify-between">
            <label className="label">Category</label>
            <button
              type="button"
              onClick={() => setAddingCategory(true)}
              className="mb-1.5 flex items-center gap-1 text-xs text-accent hover:underline"
            >
              <Plus className="size-3" /> New category
            </button>
          </div>
          <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">None</option>
            {categories.data?.map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Product</label>
          <select className="input" value={product} onChange={(e) => setProduct(e.target.value)}>
            <option value="">From category</option>
            {['broadband', 'mobile', 'dth', 'billing'].map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
        <div className="md:col-span-3">
          <label className="label">Tags (comma separated)</label>
          <input className="input" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="router, reboot, power" />
        </div>
      </Card>

      <div
        data-color-mode="dark"
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`relative rounded-xl transition ${dragging ? 'ring-2 ring-accent' : ''}`}
      >
        {dragging && (
          <div className="pointer-events-none absolute inset-0 z-10 grid place-items-center rounded-xl bg-bg/80 text-sm text-ink">
            <span className="flex items-center gap-2">
              <FileDown className="size-5 text-accent" /> Drop the markdown file to load it
            </span>
          </div>
        )}
        <MDEditor value={content} onChange={(v) => setContent(v ?? '')} height={560} preview="live" visibleDragbar={false} />
      </div>
      {addingCategory && (
        <CategoryForm category={null} onClose={() => setAddingCategory(false)} onSaved={(c) => setCategory(c.slug)} />
      )}
      <p className="mt-2 text-xs text-ink-3">
        Tip: keep the "Symptoms / Likely causes / Steps / Escalate when" sections. Each section is embedded separately, so
        clear headings make the article easier to find.
      </p>
    </div>
  )
}
