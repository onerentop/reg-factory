import { useState } from 'react'
import { Tabs, Card, Slider, InputNumber, Switch, Row, Col, Form, Select, Button, Space, message, Table, Tag, Progress } from 'antd'
import { useTheme } from '../theme/ThemeProvider'

function ConcurrencyTab() {
  const [totalMax, setTotalMax] = useState(10)
  const [outlookMax, setOutlookMax] = useState(5)
  const [gmailMax, setGmailMax] = useState(3)
  const [browserMax, setBrowserMax] = useState(8)
  const [autoProtect, setAutoProtect] = useState(true)

  return (
    <div>
      <Row gutter={24}>
        <Col span={14}>
          <Card title="并发控制" size="small">
            <div style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span>总并发任务数</span>
                <InputNumber min={1} max={50} value={totalMax} onChange={v => setTotalMax(v || 1)} />
              </div>
              <Slider min={1} max={50} value={totalMax} onChange={setTotalMax} />
            </div>
            <div style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span>Outlook 并发上限</span>
                <InputNumber min={1} max={20} value={outlookMax} onChange={v => setOutlookMax(v || 1)} />
              </div>
              <Slider min={1} max={20} value={outlookMax} onChange={setOutlookMax} />
            </div>
            <div style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span>Gmail 并发上限</span>
                <InputNumber min={1} max={20} value={gmailMax} onChange={v => setGmailMax(v || 1)} />
              </div>
              <Slider min={1} max={20} value={gmailMax} onChange={setGmailMax} />
            </div>
            <div style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span>浏览器实例上限</span>
                <InputNumber min={1} max={20} value={browserMax} onChange={v => setBrowserMax(v || 1)} />
              </div>
              <Slider min={1} max={20} value={browserMax} onChange={setBrowserMax} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>智能保护（内存 &gt;80% 自动暂停）</span>
              <Switch checked={autoProtect} onChange={setAutoProtect} />
            </div>
          </Card>
        </Col>
        <Col span={10}>
          <Card title="资源使用" size="small">
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 4 }}>CPU</div>
              <Progress percent={0} size="small" />
            </div>
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 4 }}>内存</div>
              <Progress percent={0} size="small" />
            </div>
            <div style={{ marginBottom: 16 }}>
              <div style={{ marginBottom: 4 }}>任务队列: 0 运行 / 0 排队</div>
            </div>
          </Card>
        </Col>
      </Row>
      <div style={{ marginTop: 16, textAlign: 'right' }}>
        <Button type="primary" onClick={() => {
          fetch('/api/config/concurrency', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              key: 'concurrency',
              value: { total_max: totalMax, outlook_max: outlookMax, gmail_max: gmailMax, browser_max: browserMax, auto_protect: autoProtect },
              category: 'concurrency',
            }),
          }).then(() => message.success('并发设置已保存')).catch(() => message.error('保存失败'))
        }}>保存设置</Button>
      </div>
    </div>
  )
}

function ThemeTab() {
  const { theme, setTheme } = useTheme()

  const themes = [
    { key: 'light', label: '☀️ 亮色', color: '#f8fafc' },
    { key: 'dark', label: '🌙 暗色', color: '#0f172a' },
  ]

  return (
    <Card title="主题设置" size="small">
      <div style={{ display: 'flex', gap: 16 }}>
        {themes.map(t => (
          <div
            key={t.key}
            onClick={() => setTheme(t.key as 'light' | 'dark')}
            style={{
              width: 80, height: 80, borderRadius: 12,
              background: t.color, border: theme === t.key ? '3px solid var(--accent)' : '2px solid var(--border)',
              cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexDirection: 'column', gap: 4,
            }}
          >
            <span style={{ fontSize: 20 }}>{t.label.split(' ')[0]}</span>
            <span style={{ fontSize: 10, color: theme === t.key ? 'var(--accent)' : 'var(--text-secondary)' }}>
              {t.label.split(' ')[1]}
            </span>
          </div>
        ))}
      </div>
    </Card>
  )
}

function UsersTab() {
  const columns = [
    { title: '用户名', dataIndex: 'username', key: 'username' },
    { title: '角色', dataIndex: 'role', key: 'role', render: (r: string) => <Tag>{r}</Tag> },
    { title: '状态', dataIndex: 'is_active', key: 'status', render: (a: boolean) => <Tag color={a ? 'green' : 'red'}>{a ? '启用' : '禁用'}</Tag> },
    { title: '操作', key: 'action', render: () => <Button size="small" type="link">编辑</Button> },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button type="primary">添加用户</Button>
      </div>
      <Table rowKey="id" columns={columns} dataSource={[]} pagination={false} locale={{ emptyText: '暂无用户' }} />
    </div>
  )
}

function ApiKeysTab() {
  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: 'Key', dataIndex: 'key', key: 'key', render: (k: string) => <code>{k?.slice(0, 12)}...</code> },
    { title: '权限', dataIndex: 'scopes', key: 'scopes', render: (s: string[]) => s?.map(sc => <Tag key={sc}>{sc}</Tag>) },
    { title: '调用量', dataIndex: 'call_count', key: 'calls' },
    { title: '操作', key: 'action', render: () => <Button size="small" type="link" danger>撤销</Button> },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button type="primary">创建 API Key</Button>
      </div>
      <Table rowKey="id" columns={columns} dataSource={[]} pagination={false} locale={{ emptyText: '暂无 API Key' }} />
    </div>
  )
}

export default function SettingsPage() {
  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>设置</h2>
      <Tabs items={[
        { key: 'concurrency', label: '并发控制', children: <ConcurrencyTab /> },
        { key: 'theme', label: '主题', children: <ThemeTab /> },
        { key: 'users', label: '用户管理', children: <UsersTab /> },
        { key: 'api-keys', label: 'API Key', children: <ApiKeysTab /> },
      ]} />
    </div>
  )
}
