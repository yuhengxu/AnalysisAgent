import { Routes, Route } from 'react-router-dom'
import AdminRoute from './components/AdminRoute'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Analysis from './pages/Analysis'
import Dashboard from './pages/Dashboard'
import DataCenter from './pages/DataCenter'
import Forecast from './pages/Forecast'
import Login from './pages/Login'
import LlmMonitor from './pages/LlmMonitor'
import Prediction from './pages/Prediction'
import ReportCenter from './pages/ReportCenter'
import Settings from './pages/Settings'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="data" element={<DataCenter />} />
        <Route path="analysis" element={<Analysis />} />
        <Route path="forecast" element={<Forecast />} />
        <Route path="prediction" element={<Prediction />} />
        <Route path="reports" element={<ReportCenter />} />
        <Route
          path="settings"
          element={
            <AdminRoute>
              <Settings />
            </AdminRoute>
          }
        />
        <Route
          path="monitor"
          element={
            <AdminRoute>
              <LlmMonitor />
            </AdminRoute>
          }
        />
      </Route>
    </Routes>
  )
}
