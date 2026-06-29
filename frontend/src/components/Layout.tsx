import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import FloatingAgent from './FloatingAgent'
import PredictionTaskBanner from './PredictionTaskBanner'

function UserIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden>
      <circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M5 20c0-3.314 3.134-6 7-6s7 2.686 7 6"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}

function UserMenu({
  username,
  isAdmin,
  onLogout,
}: {
  username: string
  isAdmin: boolean
  onLogout: () => void
}) {
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (menuRef.current?.contains(e.target as Node)) return
      setOpen(false)
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [open])

  return (
    <div ref={menuRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="用户菜单"
        aria-expanded={open}
        className={`flex h-9 w-9 items-center justify-center rounded-full transition ${
          open ? 'bg-white/15 text-white' : 'text-white/70 hover:bg-white/10 hover:text-white'
        }`}
      >
        <UserIcon />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-2 w-44 rounded-xl border border-white/15 bg-[#151a28] p-2 shadow-2xl">
          <div className="border-b border-white/10 px-3 py-2.5">
            <div className="truncate text-sm font-medium text-white">{username}</div>
            <div className="mt-0.5 text-xs text-white/50">{isAdmin ? '管理员' : '普通用户'}</div>
          </div>
          <button
            type="button"
            onClick={() => {
              setOpen(false)
              onLogout()
            }}
            className="mt-1 w-full rounded-lg px-3 py-2 text-left text-sm text-white/70 transition hover:bg-white/10 hover:text-white"
          >
            退出
          </button>
        </div>
      )}
    </div>
  )
}

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

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-sm transition ${
    isActive ? 'bg-brand-red/20 text-white' : 'text-white/70 hover:bg-white/10'
  }`

export default function Layout() {
  const { user, logout, isAdmin, canAccessPage } = useAuth()

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-white/10 glass">
        <div className="mx-auto flex max-w-7xl flex-nowrap items-center gap-3 px-4 py-3 lg:gap-4 lg:px-6 lg:py-4">
          <div className="flex min-w-0 shrink-0 items-center gap-3">
            <img src="/lulu.jpg" alt="水豚噜噜" className="h-9 w-9 shrink-0 rounded-full object-cover lg:h-10 lg:w-10" />
            <div className="min-w-0">
              <div className="truncate text-base font-semibold lg:text-lg">能源 AI 数据分析平台</div>
              <div className="hidden truncate text-xs text-white/60 xl:block">Energy Analysis Agent Platform</div>
            </div>
          </div>

          <div className="flex min-w-0 flex-1 items-center justify-end gap-2 lg:gap-3">
            <nav className="hidden min-w-0 flex-nowrap items-center gap-1 overflow-x-auto md:flex lg:gap-1.5">
              {navItems
                .filter((item) => canAccessPage(item.key))
                .map((item) => (
                  <NavLink key={item.to} to={item.to} className={navLinkClass}>
                    {item.label}
                  </NavLink>
                ))}
              {isAdmin &&
                adminNavItems.map((item) => (
                  <NavLink key={item.to} to={item.to} className={navLinkClass}>
                    {item.label}
                  </NavLink>
                ))}
            </nav>
            {user && <UserMenu username={user.username} isAdmin={isAdmin} onLogout={logout} />}
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
