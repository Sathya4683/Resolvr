import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, setUnauthorizedHandler, tokenStore } from './api'
import type { Role, User } from './types'

interface AuthState {
  user: User | null
  loading: boolean
  login: (username: string, password: string, role: Role) => Promise<User>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(Boolean(tokenStore.get()))

  const logout = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(logout)
    if (!tokenStore.get()) return
    //restore the session after a page reload
    api
      .get<User>('/v1/auth/me')
      .then(setUser)
      .catch(logout)
      .finally(() => setLoading(false))
  }, [logout])

  const login = async (username: string, password: string, role: Role) => {
    const res = await api.post<{ access_token: string; user: User }>('/v1/auth/login', { username, password, role })
    tokenStore.set(res.access_token)
    setUser(res.user)
    return res.user
  }

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}

export const ROLE_LABEL: Record<Role, string> = {
  support_agent: 'Support agent',
  admin: 'Admin',
  analyst: 'Analyst',
}

export function homePath(role: Role) {
  if (role === 'admin') return '/admin'
  if (role === 'analyst') return '/reviews'
  return '/tickets/new'
}
