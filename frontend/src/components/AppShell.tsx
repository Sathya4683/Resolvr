import { PanelLeftOpen } from 'lucide-react'
import { useState } from 'react'
import { Outlet } from 'react-router'
import { NotificationBell } from './NotificationBell'
import { Sidebar } from './Sidebar'

export function AppShell() {
  const [open, setOpen] = useState(() => localStorage.getItem('resolvr.sidebar') !== 'closed')
  const toggle = (value: boolean) => {
    setOpen(value)
    localStorage.setItem('resolvr.sidebar', value ? 'open' : 'closed')
  }

  return (
    <div className="flex h-full">
      {open && <Sidebar onCollapse={() => toggle(false)} />}
      <main className="relative flex min-w-0 flex-1 flex-col">
        <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex h-14 items-center justify-between px-4">
          <div className="pointer-events-auto">
            {!open && (
              <button
                onClick={() => toggle(true)}
                className="rounded-md border border-line bg-panel p-1.5 text-ink-3 hover:text-ink"
                title="Show sidebar"
              >
                <PanelLeftOpen className="size-4" />
              </button>
            )}
          </div>
          <div className="pointer-events-auto">
            <NotificationBell />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
