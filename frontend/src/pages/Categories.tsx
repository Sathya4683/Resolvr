import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { FolderPlus, Pencil, Wand2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { SeverityIcon } from '../components/badges'
import { Badge, Button, Card, Modal, Mono, PageHeader, Skeleton } from '../components/ui'
import { api } from '../lib/api'
import { titleCase } from '../lib/format'
import type { Category, Severity } from '../lib/types'

interface Candidate {
  ref: string
  subject: string | null
  snippet: string
  current_category: string | null
  similarity: number
}

export default function Categories() {
  const qc = useQueryClient()
  const [editing, setEditing] = useState<Category | 'new' | null>(null)
  const [relabel, setRelabel] = useState<Category | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['categories', 'all'],
    queryFn: () => api.get<Category[]>('/v1/categories?include_inactive=true'),
  })

  const toggle = useMutation({
    mutationFn: (c: Category) => api.patch<Category>(`/v1/categories/${c.id}`, { is_active: !c.is_active }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ['categories'] })
      toast.success(c.is_active ? `${c.name} is active again` : `${c.name} switched off for new complaints`)
    },
  })

  return (
    <div className="mx-auto max-w-6xl px-6 pt-16 pb-16">
      <PageHeader
        title="Categories"
        subtitle="The taxonomy lives in the database. Changes reach the classifier on the very next complaint, no redeploy."
        actions={
          <Button variant="primary" icon={<FolderPlus className="size-4" />} onClick={() => setEditing('new')}>
            New category
          </Button>
        }
      />
      {isLoading ? (
        <Skeleton className="h-96" />
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-line bg-panel text-left text-xs text-ink-3">
              <tr>
                <th className="px-4 py-2.5 font-medium">Category</th>
                <th className="px-4 py-2.5 font-medium">Product</th>
                <th className="px-4 py-2.5 font-medium">Usual severity</th>
                <th className="px-4 py-2.5 text-right font-medium">Tickets</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data?.map((c) => (
                <tr key={c.id} className={clsx('hover:bg-raised/40', !c.is_active && 'opacity-50')}>
                  <td className="px-4 py-3">
                    <div className="font-medium">{c.name}</div>
                    <Mono className="text-ink-3">{c.slug}</Mono>
                    <div className="mt-1 line-clamp-1 max-w-md text-xs text-ink-3">{c.description}</div>
                  </td>
                  <td className="px-4 py-3 text-ink-2">{titleCase(c.product) || 'Any'}</td>
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-2 text-ink-2">
                      <SeverityIcon severity={c.default_severity} />
                      {titleCase(c.default_severity)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-ink-2 tabular-nums">{c.ticket_count}</td>
                  <td className="px-4 py-3">
                    <button onClick={() => toggle.mutate(c)} title="Toggle active">
                      {c.is_active ? <Badge tone="ok">Active</Badge> : <Badge>Inactive</Badge>}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" icon={<Wand2 className="size-3.5" />} onClick={() => setRelabel(c)}>
                        Find tickets
                      </Button>
                      <Button size="sm" variant="ghost" icon={<Pencil className="size-3.5" />} onClick={() => setEditing(c)} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {editing && <CategoryForm category={editing === 'new' ? null : editing} onClose={() => setEditing(null)} />}
      {relabel && <RelabelModal category={relabel} onClose={() => setRelabel(null)} />}
    </div>
  )
}

function CategoryForm({ category, onClose }: { category: Category | null; onClose: () => void }) {
  const qc = useQueryClient()
  const [name, setName] = useState(category?.name ?? '')
  const [description, setDescription] = useState(category?.description ?? '')
  const [product, setProduct] = useState(category?.product ?? '')
  const [severity, setSeverity] = useState<Severity>(category?.default_severity ?? 'medium')

  const save = useMutation({
    mutationFn: () => {
      const body = { name, description, product: product || null, default_severity: severity }
      return category ? api.patch(`/v1/categories/${category.id}`, body) : api.post('/v1/categories', body)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['categories'] })
      toast.success(category ? 'Category updated' : 'Category added, the classifier can use it now')
      onClose()
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <Modal
      open
      onClose={onClose}
      title={category ? `Edit ${category.name}` : 'New category'}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div>
          <label className="label">Name</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="5G Home Router Issues" />
        </div>
        <div>
          <label className="label">Description (the classifier reads this)</label>
          <textarea
            rows={3}
            className="input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Problems with the 5G fixed wireless home router: weak signal, falling back to 4G, SIM not detected..."
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Product</label>
            <select className="input" value={product} onChange={(e) => setProduct(e.target.value)}>
              <option value="">Any</option>
              {['broadband', 'mobile', 'dth', 'billing'].map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Usual severity</label>
            <select className="input" value={severity} onChange={(e) => setSeverity(e.target.value as Severity)}>
              {['low', 'medium', 'high', 'critical'].map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </Modal>
  )
}

function RelabelModal({ category, onClose }: { category: Category; onClose: () => void }) {
  const qc = useQueryClient()
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const { data, isLoading } = useQuery({
    queryKey: ['categories', category.id, 'candidates'],
    queryFn: () => api.get<Candidate[]>(`/v1/categories/${category.id}/candidates?limit=25`),
  })
  const move = useMutation({
    mutationFn: () => api.post<{ updated: number }>(`/v1/categories/${category.id}/relabel`, { refs: [...picked] }),
    onSuccess: (r) => {
      toast.success(`Moved ${r.updated} tickets to ${category.name}`)
      qc.invalidateQueries({ queryKey: ['categories'] })
      onClose()
    },
  })

  return (
    <Modal
      open
      onClose={onClose}
      width="max-w-3xl"
      title={`Tickets that look like "${category.name}"`}
      footer={
        <>
          <span className="mr-auto self-center text-xs text-ink-3">{picked.size} selected</span>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!picked.size} loading={move.isPending} onClick={() => move.mutate()}>
            Move to {category.name}
          </Button>
        </>
      }
    >
      <p className="mb-3 text-sm text-ink-3">
        Older tickets were filed before this class existed. These are the closest matches to its description (semantic
        search). Pick the ones that belong here.
      </p>
      {isLoading ? (
        <Skeleton className="h-64" />
      ) : (
        <div className="space-y-1.5">
          {data?.map((c) => (
            <label
              key={c.ref}
              className={clsx(
                'flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition',
                picked.has(c.ref) ? 'border-accent/40 bg-accent/5' : 'border-line hover:bg-raised/40',
              )}
            >
              <input
                type="checkbox"
                className="mt-1 accent-[#6366f1]"
                checked={picked.has(c.ref)}
                onChange={() => {
                  const next = new Set(picked)
                  if (next.has(c.ref)) next.delete(c.ref)
                  else next.add(c.ref)
                  setPicked(next)
                }}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-xs">
                  <Mono className="text-ink-2">{c.ref}</Mono>
                  <span className="text-ink-3">now in {c.current_category ?? 'no category'}</span>
                  <span className="ml-auto text-ink-3 tabular-nums">{Math.round(c.similarity * 100)}% match</span>
                </div>
                <div className="mt-0.5 line-clamp-1 text-sm text-ink-2">{c.snippet}</div>
              </div>
            </label>
          ))}
        </div>
      )}
    </Modal>
  )
}
