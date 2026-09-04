import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { GlobalOutlined, GoogleOutlined, MailOutlined, MessageOutlined } from '@ant-design/icons'
import { Tooltip } from 'antd'
import styles from './MainLayout.module.css'

const navItems = [
  { key: '/accounts/outlook', icon: <MailOutlined />, label: 'Outlook' },
  { key: '/accounts/google', icon: <GoogleOutlined />, label: 'Google' },
  { key: '/sms', icon: <MessageOutlined />, label: '接码平台' },
  { key: '/proxy', icon: <GlobalOutlined />, label: '代理' },
]

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <div className={styles.layout}>
      <aside className={styles.iconSidebar}>
        <div className={styles.logo}>🏭</div>
        {navItems.map((item) => (
          <Tooltip key={item.key} title={item.label} placement="right">
            <div
              className={`${styles.iconItem} ${location.pathname.startsWith(item.key) ? styles.active : ''}`}
              onClick={() => navigate(item.key)}
            >
              {item.icon}
            </div>
          </Tooltip>
        ))}
      </aside>
      <main className={styles.content}>
        <Outlet />
      </main>
    </div>
  )
}
