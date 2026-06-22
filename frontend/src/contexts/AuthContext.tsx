import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { getMe, login as apiLogin } from '../api/client'
import { AuthUser, getStoredToken, getStoredUser, setStoredToken, setStoredUser } from '../lib/authStorage'

interface AuthContextValue {
  user: AuthUser | null
  token: string | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  isAdmin: boolean
  canAccessPage: (page: string) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(getStoredUser())
  const [token, setToken] = useState<string | null>(getStoredToken())
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const t = getStoredToken()
    if (!t) {
      setLoading(false)
      return
    }
    getMe()
      .then((u) => {
        setUser(u)
        setStoredUser(u)
      })
      .catch(() => {
        setStoredToken(null)
        setStoredUser(null)
        setUser(null)
        setToken(null)
      })
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const res = await apiLogin(username, password)
    setStoredToken(res.access_token)
    setStoredUser(res.user)
    setToken(res.access_token)
    setUser(res.user)
  }, [])

  const logout = useCallback(() => {
    setStoredToken(null)
    setStoredUser(null)
    setToken(null)
    setUser(null)
  }, [])

  const canAccessPage = useCallback(
    (page: string) => user?.role === 'admin' || Boolean(user?.allowed_pages?.includes(page)),
    [user],
  )

  const value = useMemo(
    () => ({
      user,
      token,
      loading,
      login,
      logout,
      isAdmin: user?.role === 'admin',
      canAccessPage,
    }),
    [user, token, loading, login, logout, canAccessPage],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
