const TOKEN_KEY = 'auth_token'

export interface AuthUser {
  id: number
  username: string
  role: 'admin' | 'user'
  allowed_pages: string[]
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setStoredToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function getStoredUser(): AuthUser | null {
  const raw = localStorage.getItem('auth_user')
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthUser
  } catch {
    return null
  }
}

export function setStoredUser(user: AuthUser | null) {
  if (user) localStorage.setItem('auth_user', JSON.stringify(user))
  else localStorage.removeItem('auth_user')
}
