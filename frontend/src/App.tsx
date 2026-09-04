import { Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import AccountsPage from './pages/AccountsPage'
import SmsConfigPage from './pages/SmsConfigPage'
import ProxyPage from './pages/ProxyPage'
import LoginPage from './pages/LoginPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<MainLayout />}>
        <Route path="/" element={<Navigate to="/accounts/outlook" replace />} />
        <Route path="/accounts/:platform" element={<AccountsPage />} />
        <Route path="/sms" element={<SmsConfigPage />} />
        <Route path="/proxy" element={<ProxyPage />} />
        <Route path="*" element={<Navigate to="/accounts/outlook" replace />} />
      </Route>
    </Routes>
  )
}
