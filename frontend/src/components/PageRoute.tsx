import { Navigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function PageRoute({
  page,
  children,
}: {
  page: string
  children: React.ReactNode
}) {
  const { user, loading, canAccessPage } = useAuth()

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-white/60">
        加载中…
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  if (!canAccessPage(page)) {
    return (
      <div className="py-16 text-center">
        <div className="text-lg font-medium text-white/90">无权访问</div>
        <p className="mt-2 text-sm text-white/50">请联系管理员开通该页面权限</p>
      </div>
    )
  }

  return <>{children}</>
}
