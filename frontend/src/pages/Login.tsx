import clsx from 'clsx'
import { ArrowRight, BarChart3, ChevronDown, Headset, Lock, ShieldCheck, User as UserIcon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router'
import { LogoMark } from '../components/Logo'
import { Button } from '../components/ui'
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
    a: 'Paste a customer complaint and Resolvr labels it (category, product, severity, sentiment), finds the most similar past tickets and help articles, and drafts step-by-step fixes with citations.',
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
  const [openFaq, setOpenFaq] = useState<number | null>(0)

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
    <div className="grid min-h-full lg:grid-cols-2">
      {/* left: what resolvr is */}
      <section className="relative hidden overflow-hidden border-r border-line bg-panel lg:flex lg:flex-col">
        <div className="pointer-events-none absolute -top-40 -left-40 size-[520px] rounded-full bg-accent-strong/20 blur-3xl" />
        <div className="pointer-events-none absolute -right-32 bottom-0 size-[420px] rounded-full bg-info/10 blur-3xl" />
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage: 'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)',
            backgroundSize: '44px 44px',
          }}
        />
        <div className="relative flex flex-1 flex-col justify-between p-12 xl:p-16">
          <div className="flex items-center gap-3">
            <LogoMark className="size-10" />
            <span className="text-2xl font-semibold tracking-tight">Resolvr</span>
          </div>

          <div className="max-w-lg">
            <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-line bg-card/60 px-3 py-1 text-xs text-ink-2">
              <span className="size-1.5 rounded-full bg-ok" />
              Telecom support desk assistant
            </p>
            <h1 className="text-4xl leading-tight font-semibold tracking-tight xl:text-[2.75rem]">
              Every complaint, matched to the fix that{' '}
              <span className="bg-gradient-to-r from-accent to-info bg-clip-text text-transparent">already worked</span>.
            </h1>
            <p className="mt-4 text-base leading-relaxed text-ink-2">
              Semantic search over past tickets and the knowledge base, grounded AI drafts with citations, and a human in the
              loop for anything sensitive.
            </p>

            <div className="mt-10 space-y-2">
              {FAQS.map((f, i) => (
                <div key={f.q} className="rounded-xl border border-line bg-card/50 backdrop-blur">
                  <button
                    onClick={() => setOpenFaq(openFaq === i ? null : i)}
                    className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left text-sm font-medium"
                  >
                    {f.q}
                    <ChevronDown
                      className={clsx('size-4 shrink-0 text-ink-3 transition-transform', openFaq === i && 'rotate-180')}
                    />
                  </button>
                  {openFaq === i && <p className="px-4 pb-4 text-sm leading-relaxed text-ink-2">{f.a}</p>}
                </div>
              ))}
            </div>
          </div>

          <p className="text-xs text-ink-3">Broadband · Mobile · DTH · Billing</p>
        </div>
      </section>

      {/* right: sign in */}
      <section className="flex items-center justify-center p-6 sm:p-12">
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
