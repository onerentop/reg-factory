import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import {
  DashboardOutlined,
  MailOutlined,
  GoogleOutlined,
  MessageOutlined,
  GlobalOutlined,
  SettingOutlined,
  FileTextOutlined,
  BellOutlined,
  AuditOutlined,
  ClockCircleOutlined,
  ToolOutlined,
} from '@ant-design/icons'
import { Tooltip } from 'antd'
import styles from './MainLayout.module.css'

const navItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/sms', icon: <MessageOutlined />, label: '接码平台' },
  { key: '/accounts/outlook', icon: <MailOutlined />, label: 'Outlook' },
  { key: '/accounts/google', icon: <GoogleOutlined />, label: 'Google' },
  { key: '/proxy', icon: <GlobalOutlined />, label: '代理' },
  { key: '/logs', icon: <FileTextOutlined />, label: '日志' },
  { key: '/alerts', icon: <BellOutlined />, label: '告警' },
  { key: '/audit', icon: <AuditOutlined />, label: '审计' },
  { key: '/schedules', icon: <ClockCircleOutlined />, label: '定时任务' },
  { key: '/tools', icon: <ToolOutlined />, label: '工具/运维' },
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
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
