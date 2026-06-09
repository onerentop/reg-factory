import { Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import DashboardPage from './pages/DashboardPage'
import AccountsPage from './pages/AccountsPage'
import SmsConfigPage from './pages/SmsConfigPage'
import ProxyPage from './pages/ProxyPage'
import LogsPage from './pages/LogsPage'
import SettingsPage from './pages/SettingsPage'
import LoginPage from './pages/LoginPage'
import AlertsPage from './pages/AlertsPage'
import AuditPage from './pages/AuditPage'
import SchedulesPage from './pages/SchedulesPage'
import ImportPage from './pages/ImportPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<MainLayout />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/accounts/:platform" element={<AccountsPage />} />
        <Route path="/sms" element={<SmsConfigPage />} />
        <Route path="/proxy" element={<ProxyPage />} />
        <Route path="/logs" element={<LogsPage />} />
        <Route path="/settings/*" element={<SettingsPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/schedules" element={<SchedulesPage />} />
        <Route path="/import" element={<ImportPage />} />
      </Route>
    </Routes>
  )
}
