import { FormEvent, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function Login() {
  const { user, login } = useAuth()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const from = (location.state as { from?: string } | null)?.from || '/'

  if (user) {
    return <Navigate to={from} replace />
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
    } catch {
      setError('用户名或密码错误')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="glass w-full max-w-md rounded-2xl p-8">
        <div className="mb-6 text-center">
          <img src="/lulu.jpg" alt="水豚噜噜" className="mx-auto mb-4 h-14 w-14 rounded-full object-cover" />
          <h1 className="text-xl font-semibold">能源行业 AI 数据分析平台</h1>
          <p className="mt-1 text-sm text-white/50">请登录后继续</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs text-white/50">用户名</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-black/20 px-4 py-2.5 text-sm outline-none focus:border-brand-blue/50"
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-white/50">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-black/20 px-4 py-2.5 text-sm outline-none focus:border-brand-blue/50"
              autoComplete="current-password"
              required
            />
          </div>
          {error && <div className="text-sm text-red-400">{error}</div>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-brand-red py-2.5 text-sm font-medium disabled:opacity-50"
          >
            {loading ? '登录中…' : '登录'}
          </button>
        </form>
      </div>
    </div>
  )
}
