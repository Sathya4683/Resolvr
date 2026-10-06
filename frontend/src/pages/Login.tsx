import clsx from 'clsx'
import { ArrowRight, BarChart3, Headset, Lock, ShieldCheck, User as UserIcon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router'
import { LogoMark } from '../components/Logo'
import { Accordion, Button } from '../components/ui'
import { homePath, useAuth } from '../lib/auth'
import type { Role } from '../lib/types'

const ROLES: { value: Role; label: string; icon: typeof Headset; blurb: string }[] = [
  { value: 'support_agent', label: 'Support agent', icon: Headset, blurb: 'Analyse complaints and resolve tickets' },
  { value: 'admin', label: 'Admin', icon: ShieldCheck, blurb: 'Approve critical cases and manage knowledge' },
  { value: 'analyst', label: 'Analyst', icon: BarChart3, blurb: 'Review answer quality and citations' },
]

const FAQS = [
  {
    q: 'What does Resolvr do?',
    a: 'Paste a customer complaint and Resolvr labels it (category, product, severity, sentiment), finds the most similar past tickets and help articles, and drafts step-by-step fixes with citations!',
  },
  {
    q: 'Where do the answers come from?',
    a: "Only from your own resolved tickets and knowledge base. Every step cites its source, and if nothing relevant is found Resolvr says so instead of guessing.",
  },
  {
    q: 'Who signs off on sensitive cases?',
    a: 'Legal, regulatory, fraud, privacy and compensation cases are marked critical. An admin approves, edits or declines the draft before the agent sees it, and everyone gets notified.',
  },
  {
    q: 'Is customer data safe?',
    a: 'Phone numbers, emails, account and card numbers are masked before anything is sent to the AI model, and every sensitive action is audit logged.',
  },
  {
    q: 'What do analysts do?',
    a: 'They review samples of AI answers for correctness and citation quality. Their notes are fed back into future answers straight away.',
  },
]

export default function Login() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [role, setRole] = useState<Role>('support_agent')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  if (user) return <Navigate to={homePath(user.role)} replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const u = await login(username.trim(), password, role)
      navigate(homePath(u.role), { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid min-h-full lg:h-screen lg:grid-cols-2 lg:overflow-hidden">
      {/* left: what resolvr is, fixed to the viewport height and scrolls on its own */}
      <section className="relative hidden border-r border-line bg-panel lg:block lg:h-screen lg:overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,rgba(99,102,241,0.14),transparent_55%)]" />
        <div className="relative h-full overflow-y-auto [scrollbar-gutter:stable]">
          <div className="flex min-h-full flex-col px-12 py-12 xl:px-16">
            <div className="flex items-center gap-3">
              <LogoMark className="size-9" />
              <span className="text-xl font-semibold tracking-tight">Resolvr</span>
            </div>

            <div className="mt-20 max-w-lg">
              <p className="text-xs font-semibold tracking-[0.14em] text-ink-3 uppercase">Telecom support desk</p>
              <h1 className="mt-4 text-4xl leading-[1.15] font-semibold tracking-tight">
                Every complaint, matched to the fix that already worked.
              </h1>
              <p className="mt-4 text-base leading-relaxed text-ink-2">
                Semantic search over past tickets and the knowledge base, AI drafts that cite their sources, and an admin in
                the loop for anything sensitive.
              </p>

              <div className="mt-14">
                <h2 className="mb-2 text-sm font-semibold text-ink">Frequently asked questions</h2>
                <Accordion items={FAQS.map((f) => ({ title: f.q, body: f.a }))} />
              </div>
            </div>

            <p className="mt-auto pt-12 text-xs text-ink-3">Broadband · Mobile · DTH · Billing</p>
          </div>
        </div>
      </section>

      {/* right: sign in */}
      <section className="flex items-center justify-center p-6 sm:p-12 lg:h-screen lg:overflow-y-auto">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <LogoMark className="size-9" />
            <span className="text-xl font-semibold">Resolvr</span>
          </div>
          <h2 className="text-2xl font-semibold tracking-tight">Sign in</h2>
          <p className="mt-1.5 text-sm text-ink-3">Choose your role and use the account your admin set up.</p>

          <div className="mt-8 grid grid-cols-3 gap-2">
            {ROLES.map((r) => (
              <button
                key={r.value}
                type="button"
                onClick={() => setRole(r.value)}
                className={clsx(
                  'flex flex-col items-center gap-2 rounded-xl border px-2 py-4 text-xs font-medium transition',
                  role === r.value
                    ? 'border-accent/60 bg-accent/10 text-ink shadow-[0_0_0_3px_rgba(128,131,255,0.12)]'
                    : 'border-line bg-card text-ink-2 hover:border-line-strong hover:text-ink',
                )}
              >
                <r.icon className={clsx('size-5', role === r.value ? 'text-accent' : 'text-ink-3')} />
                {r.label}
              </button>
            ))}
          </div>
          <p className="mt-2.5 text-center text-xs text-ink-3">{ROLES.find((r) => r.value === role)!.blurb}</p>

          <form onSubmit={submit} className="mt-8 space-y-4">
            <div>
              <label className="label" htmlFor="username">
                Username
              </label>
              <div className="relative">
                <UserIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
                <input
                  id="username"
                  className="input h-11 pl-9"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoFocus
                  required
                />
              </div>
            </div>
            <div>
              <label className="label" htmlFor="password">
                Password
              </label>
              <div className="relative">
                <Lock className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
                <input
                  id="password"
                  type="password"
                  className="input h-11 pl-9"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
            </div>
            {error && (
              <div className="rounded-lg border border-danger/25 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</div>
            )}
            <Button type="submit" variant="primary" size="lg" className="w-full" loading={loading}>
              Continue as {ROLES.find((r) => r.value === role)!.label.toLowerCase()}
              {!loading && <ArrowRight className="size-4" />}
            </Button>
          </form>
        </div>
      </section>
    </div>
  )
}
