import { Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import { AppShell } from './components/AppShell'
import { EmptyState } from './components/ui'
import { homePath, useAuth } from './lib/auth'
import type { Role } from './lib/types'
import Login from './pages/Login'
import NewTicket from './pages/NewTicket'
import TicketDetail from './pages/TicketDetail'

function RequireAuth({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading)
    return (
      <div className="grid h-full place-items-center">
        <Loader2 className="size-5 animate-spin text-ink-3" />
      </div>
    )
  if (!user) return <Navigate to="/login" replace />
  if (roles && !roles.includes(user.role)) return <Navigate to={homePath(user.role)} replace />
  return <>{children}</>
}

function Home() {
  const { user } = useAuth()
  return <Navigate to={user ? homePath(user.role) : '/login'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<Home />} />
        <Route
          path="tickets/new"
          element={
            <RequireAuth roles={['support_agent', 'admin']}>
              <NewTicket />
            </RequireAuth>
          }
        />
        <Route path="tickets/:ref" element={<TicketDetail />} />
        <Route
          path="*"
          element={<EmptyState icon={<span>404</span>} title="Page not found" text="That page doesn't exist." />}
        />
      </Route>
    </Routes>
  )
}
