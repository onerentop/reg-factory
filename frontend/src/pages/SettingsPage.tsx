import { Card, Tabs } from 'antd'

export default function SettingsPage() {
  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>设置</h2>
      <Tabs items={[
        { key: 'concurrency', label: '并发控制', children: <Card>并发设置（待实现）</Card> },
        { key: 'theme', label: '主题', children: <Card>主题设置（待实现）</Card> },
        { key: 'users', label: '用户管理', children: <Card>用户管理（待实现）</Card> },
        { key: 'api-keys', label: 'API Key', children: <Card>API Key 管理（待实现）</Card> },
      ]} />
    </div>
  )
}
