import { Routes, Route } from 'react-router-dom'
import AdminRoute from './components/AdminRoute'
import Layout from './components/Layout'
import PageRoute from './components/PageRoute'
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
import UserManagement from './pages/UserManagement'

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
        <Route
          index
          element={
            <PageRoute page="dashboard">
              <Dashboard />
            </PageRoute>
          }
        />
        <Route
          path="data"
          element={
            <PageRoute page="data">
              <DataCenter />
            </PageRoute>
          }
        />
        <Route
          path="analysis"
          element={
            <PageRoute page="analysis">
              <Analysis />
            </PageRoute>
          }
        />
        <Route
          path="forecast"
          element={
            <PageRoute page="forecast">
              <Forecast />
            </PageRoute>
          }
        />
        <Route
          path="prediction"
          element={
            <PageRoute page="prediction">
              <Prediction />
            </PageRoute>
          }
        />
        <Route
          path="reports"
          element={
            <PageRoute page="reports">
              <ReportCenter />
            </PageRoute>
          }
        />
        <Route
          path="users"
          element={
            <AdminRoute>
              <UserManagement />
            </AdminRoute>
          }
        />
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
