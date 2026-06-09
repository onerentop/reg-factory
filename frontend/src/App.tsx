import { Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import DashboardPage from './pages/DashboardPage'
import AccountsPage from './pages/AccountsPage'
import SmsConfigPage from './pages/SmsConfigPage'
import ProxyPage from './pages/ProxyPage'
import LogsPage from './pages/LogsPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/accounts/:platform" element={<AccountsPage />} />
        <Route path="/sms" element={<SmsConfigPage />} />
        <Route path="/proxy" element={<ProxyPage />} />
        <Route path="/logs" element={<LogsPage />} />
        <Route path="/settings/*" element={<SettingsPage />} />
      </Route>
    </Routes>
  )
}
