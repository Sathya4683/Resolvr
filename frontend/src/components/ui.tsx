import clsx from 'clsx'
import { Loader2, X } from 'lucide-react'
import { useEffect, type ButtonHTMLAttributes, type ReactNode } from 'react'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success'

const buttonStyles: Record<ButtonVariant, string> = {
  primary: 'bg-accent-strong text-white hover:bg-accent shadow-[0_0_0_1px_rgba(255,255,255,0.06)_inset]',
  secondary: 'bg-raised text-ink border border-line hover:bg-hover hover:border-line-strong',
  ghost: 'text-ink-2 hover:text-ink hover:bg-raised',
  danger: 'bg-danger/10 text-danger border border-danger/25 hover:bg-danger/20',
  success: 'bg-ok/10 text-ok border border-ok/25 hover:bg-ok/20',
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  icon?: ReactNode
}) {
  return (
    <button
      className={clsx(
        'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40',
        size === 'sm' && 'h-8 px-3 text-xs',
        size === 'md' && 'h-9 px-3.5 text-sm',
        size === 'lg' && 'h-11 px-5 text-sm',
        buttonStyles[variant],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  )
}

const tones = {
  neutral: 'bg-raised text-ink-2 border-line',
  accent: 'bg-accent/10 text-accent border-accent/25',
  ok: 'bg-ok/10 text-ok border-ok/25',
  warn: 'bg-warn/10 text-warn border-warn/25',
  high: 'bg-high/10 text-high border-high/25',
  danger: 'bg-danger/10 text-danger border-danger/25',
  info: 'bg-info/10 text-info border-info/25',
}
export type Tone = keyof typeof tones

export function Badge({
  tone = 'neutral',
  icon,
  children,
  className,
  title,
}: {
  tone?: Tone
  icon?: ReactNode
  children: ReactNode
  className?: string
  title?: string
}) {
  return (
    <span
      title={title}
      className={clsx(
        'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        tones[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  )
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx('card', className)}>{children}</div>
}

export function CardHeader({
  title,
  subtitle,
  icon,
  action,
}: {
  title: ReactNode
  subtitle?: ReactNode
  icon?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-3.5">
      <div className="flex items-center gap-2.5">
        {icon && <span className="text-ink-3">{icon}</span>}
        <div>
          <h3 className="text-sm font-semibold text-ink">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  )
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx('size-4 animate-spin text-ink-3', className)} />
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={clsx('relative overflow-hidden rounded-md bg-raised', className)}>
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.6s_infinite] bg-gradient-to-r from-transparent via-white/[0.04] to-transparent" />
    </div>
  )
}

export function EmptyState({
  icon,
  title,
  text,
  action,
}: {
  icon: ReactNode
  title: string
  text?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-4 grid size-12 place-items-center rounded-xl border border-line bg-raised text-ink-3">{icon}</div>
      <h3 className="text-sm font-semibold">{title}</h3>
      {text && <p className="mt-1 max-w-sm text-sm text-ink-3">{text}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  width = 'max-w-lg',
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  footer?: ReactNode
  width?: string
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className={clsx('w-full rounded-2xl border border-line bg-card shadow-2xl', width)}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button onClick={onClose} className="rounded-md p-1 text-ink-3 hover:bg-raised hover:text-ink">
            <X className="size-4" />
          </button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  )
}

export function Drawer({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  children: ReactNode
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  return (
    <>
      <div
        className={clsx(
          'fixed inset-0 z-40 bg-black/50 transition-opacity',
          open ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
        onClick={onClose}
      />
      <aside
        className={clsx(
          'fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-line bg-panel shadow-2xl transition-transform duration-200',
          open ? 'translate-x-0' : 'translate-x-full',
        )}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div className="min-w-0 text-sm font-semibold">{title}</div>
          <button onClick={onClose} className="rounded-md p-1 text-ink-3 hover:bg-raised hover:text-ink">
            <X className="size-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </aside>
    </>
  )
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-3">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Stat({
  label,
  value,
  hint,
  icon,
  tone = 'neutral',
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  icon?: ReactNode
  tone?: Tone
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-ink-3">{label}</span>
        {icon && <span className={clsx('rounded-md border p-1.5', tones[tone])}>{icon}</span>}
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight">{value}</div>
      {hint && <div className="mt-1 text-xs text-ink-3">{hint}</div>}
    </div>
  )
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={clsx('font-mono text-[0.8em] tracking-tight', className)}>{children}</span>
}

export function Tabs<T extends string>({
  value,
  onChange,
  items,
}: {
  value: T
  onChange: (v: T) => void
  items: { value: T; label: ReactNode }[]
}) {
  return (
    <div className="inline-flex rounded-lg border border-line bg-panel p-1">
      {items.map((item) => (
        <button
          key={item.value}
          onClick={() => onChange(item.value)}
          className={clsx(
            'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
            value === item.value ? 'bg-raised text-ink shadow-sm' : 'text-ink-3 hover:text-ink-2',
          )}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
