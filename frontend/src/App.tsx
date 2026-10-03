import { Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import { AppShell } from './components/AppShell'
import { EmptyState } from './components/ui'
import { homePath, useAuth } from './lib/auth'
import type { Role } from './lib/types'
import { Audit, Users } from './pages/AdminPages'
import Approvals from './pages/Approvals'
import Assistant from './pages/Assistant'
import Batch from './pages/Batch'
import Categories from './pages/Categories'
import DataImport from './pages/DataImport'
import { KnowledgeArticle, KnowledgeList } from './pages/Knowledge'
import KnowledgeEditor from './pages/KnowledgeEditor'
import Login from './pages/Login'
import NewTicket from './pages/NewTicket'
import Overview from './pages/Overview'
import Quality from './pages/Quality'
import Reports from './pages/Reports'
import Reviews from './pages/Reviews'
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
          path="assistant"
          element={
            <RequireAuth roles={['support_agent', 'admin']}>
              <Assistant />
            </RequireAuth>
          }
        />
        <Route
          path="batch"
          element={
            <RequireAuth roles={['support_agent', 'admin']}>
              <Batch />
            </RequireAuth>
          }
        />
        <Route
          path="approvals"
          element={
            <RequireAuth roles={['admin']}>
              <Approvals />
            </RequireAuth>
          }
        />
        <Route path="admin" element={<RequireAuth roles={['admin']}><Overview /></RequireAuth>} />
        <Route path="categories" element={<RequireAuth roles={['admin']}><Categories /></RequireAuth>} />
        <Route path="data" element={<RequireAuth roles={['admin']}><DataImport /></RequireAuth>} />
        <Route path="users" element={<RequireAuth roles={['admin']}><Users /></RequireAuth>} />
        <Route path="audit" element={<RequireAuth roles={['admin']}><Audit /></RequireAuth>} />
        <Route path="reviews" element={<RequireAuth roles={['analyst']}><Reviews /></RequireAuth>} />
        <Route path="quality" element={<RequireAuth roles={['admin', 'analyst']}><Quality /></RequireAuth>} />
        <Route path="reports" element={<RequireAuth roles={['admin', 'analyst']}><Reports /></RequireAuth>} />
        <Route path="knowledge" element={<KnowledgeList />} />
        <Route path="knowledge/new" element={<RequireAuth roles={['admin', 'analyst']}><KnowledgeEditor /></RequireAuth>} />
        <Route path="knowledge/:ref" element={<KnowledgeArticle />} />
        <Route path="knowledge/:ref/edit" element={<RequireAuth roles={['admin', 'analyst']}><KnowledgeEditor /></RequireAuth>} />
        <Route
          path="*"
          element={<EmptyState icon={<span>404</span>} title="Page not found" text="That page doesn't exist." />}
        />
      </Route>
    </Routes>
  )
}
