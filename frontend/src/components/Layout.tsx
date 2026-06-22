import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import FloatingAgent from './FloatingAgent'
import PredictionTaskBanner from './PredictionTaskBanner'

const navItems = [
  { key: 'dashboard', to: '/', label: '总览' },
  { key: 'data', to: '/data', label: '数据中心' },
  { key: 'analysis', to: '/analysis', label: '智能分析' },
  { key: 'prediction', to: '/prediction', label: '预测分析表' },
  { key: 'forecast', to: '/forecast', label: '预测模型' },
  { key: 'reports', to: '/reports', label: '报告中心' },
]

const adminNavItems = [
  { to: '/users', label: '用户管理' },
  { to: '/settings', label: '系统设置' },
  { to: '/monitor', label: '监控日志' },
]

export default function Layout() {
  const { user, logout, isAdmin, canAccessPage } = useAuth()

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-white/10 glass">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <img src="/logo.jpg" alt="logo" className="h-10 w-10 rounded-full object-cover" />
            <div>
              <div className="text-lg font-semibold">能源行业 AI 数据分析平台</div>
              <div className="text-xs text-white/60">Energy Analysis Agent Platform</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <nav className="hidden gap-2 md:flex">
              {navItems
                .filter((item) => canAccessPage(item.key))
                .map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      `rounded-full px-4 py-2 text-sm transition ${
                        isActive ? 'bg-brand-red/20 text-white' : 'text-white/70 hover:bg-white/10'
                      }`
                    }
                  >
                    {item.label}
                  </NavLink>
                ))}
              {isAdmin &&
                adminNavItems.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      `rounded-full px-4 py-2 text-sm transition ${
                        isActive ? 'bg-brand-red/20 text-white' : 'text-white/70 hover:bg-white/10'
                      }`
                    }
                  >
                    {item.label}
                  </NavLink>
                ))}
            </nav>
            {user && (
              <div className="flex items-center gap-2 text-sm">
                <span className="hidden text-white/60 sm:inline">
                  {user.username}
                  {isAdmin ? ' · 管理员' : ''}
                </span>
                <button
                  type="button"
                  onClick={logout}
                  className="rounded-lg bg-white/10 px-3 py-1.5 text-xs hover:bg-white/15"
                >
                  退出
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      <PredictionTaskBanner />
      <main className="mx-auto max-w-7xl px-6 py-8 pb-28">
        <Outlet />
      </main>
      <FloatingAgent />
    </div>
  )
}
