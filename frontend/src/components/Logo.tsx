import clsx from 'clsx'

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={clsx('size-7', className)} aria-hidden>
      <defs>
        <linearGradient id="logo-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#9a9cff" />
          <stop offset="1" stopColor="#5b5bf0" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#logo-g)" />
      <path
        d="M10 22V10h6.5a4 4 0 0 1 0 8H13m3.5 0L21 22"
        fill="none"
        stroke="#fff"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function Logo({ size = 'md' }: { size?: 'md' | 'lg' }) {
  return (
    <div className="flex items-center gap-2.5">
      <LogoMark className={size === 'lg' ? 'size-9' : 'size-7'} />
      <span className={clsx('font-semibold tracking-tight', size === 'lg' ? 'text-xl' : 'text-[15px]')}>Resolvr</span>
    </div>
  )
}
