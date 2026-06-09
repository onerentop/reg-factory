import { useState, useEffect } from 'react'
import { Tabs, Card, Slider, InputNumber, Switch, Row, Col, Form, Select, Button, message, Table, Tag, Progress, Modal, Input } from 'antd'
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
    { key: 'cyberpunk', label: '💜 赛博紫', color: '#0f0a2a' },
    { key: 'terminal', label: '🌿 终端绿', color: '#052e16' },
  ]

  return (
    <Card title="主题设置" size="small">
      <div style={{ display: 'flex', gap: 16 }}>
        {themes.map(t => (
          <div
            key={t.key}
            onClick={() => setTheme(t.key as 'light' | 'dark' | 'cyberpunk' | 'terminal')}
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
  const [users, setUsers] = useState<any[]>([])
  const [addVisible, setAddVisible] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => {
    fetch('/api/auth/users').then(r => r.json())
      .then(res => setUsers(res.data || []))
      .catch(() => {})
  }, [])

  const addUser = async () => {
    const values = await form.validateFields()
    await fetch('/api/auth/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(values),
    })
    message.success('用户已创建')
    setAddVisible(false)
    form.resetFields()
    fetch('/api/auth/users').then(r => r.json()).then(res => setUsers(res.data || []))
  }

  const columns = [
    { title: '用户名', dataIndex: 'username', key: 'username' },
    { title: '角色', dataIndex: 'role', key: 'role', render: (r: string) => <Tag>{r}</Tag> },
    { title: '状态', dataIndex: 'is_active', key: 'status', render: (a: boolean) => <Tag color={a ? 'green' : 'red'}>{a ? '启用' : '禁用'}</Tag> },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button type="primary" onClick={() => setAddVisible(true)}>添加用户</Button>
      </div>
      <Table rowKey="id" columns={columns} dataSource={users} pagination={false} />
      <Modal title="添加用户" open={addVisible} onOk={addUser} onCancel={() => setAddVisible(false)}>
        <Form form={form} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, min: 6 }]}><Input.Password /></Form.Item>
          <Form.Item name="role" label="角色" initialValue="readonly">
            <Select options={[
              { value: 'admin', label: '管理员' },
              { value: 'operator', label: '操作员' },
              { value: 'readonly', label: '只读' },
            ]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

function ApiKeysTab() {
  const [keys, setKeys] = useState<any[]>([])
  const [addVisible, setAddVisible] = useState(false)
  const [form] = Form.useForm()

  const fetchKeys = () => {
    fetch('/api/auth/api-keys?owner_id=system').then(r => r.json())
      .then(res => setKeys(res.data || []))
      .catch(() => {})
  }

  useEffect(() => { fetchKeys() }, [])

  const createKey = async () => {
    const values = await form.validateFields()
    await fetch('/api/auth/api-keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(values),
    })
    message.success('API Key 已创建')
    setAddVisible(false)
    form.resetFields()
    fetchKeys()
  }

  const revokeKey = async (keyId: string) => {
    await fetch(`/api/auth/api-keys/${keyId}`, { method: 'DELETE' })
    message.success('已撤销')
    fetchKeys()
  }

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: 'Key', dataIndex: 'key', key: 'key', render: (k: string) => <code>{k?.slice(0, 16)}...</code> },
    { title: '权限', dataIndex: 'scopes', key: 'scopes', render: (s: string[]) => s?.map(sc => <Tag key={sc}>{sc}</Tag>) || '-' },
    { title: '调用量', dataIndex: 'call_count', key: 'calls' },
    { title: '状态', dataIndex: 'is_active', key: 'active', render: (a: boolean) => <Tag color={a ? 'green' : 'red'}>{a ? '有效' : '已撤销'}</Tag> },
    { title: '操作', key: 'action', render: (_: any, record: any) => record.is_active && <Button size="small" type="link" danger onClick={() => revokeKey(record.id)}>撤销</Button> },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button type="primary" onClick={() => setAddVisible(true)}>创建 API Key</Button>
      </div>
      <Table rowKey="id" columns={columns} dataSource={keys} pagination={false} />
      <Modal title="创建 API Key" open={addVisible} onOk={createKey} onCancel={() => setAddVisible(false)}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="scopes" label="权限范围">
            <Select mode="multiple" options={[
              { value: 'sms', label: 'SMS Service' },
              { value: 'account', label: 'Account Service' },
              { value: 'config', label: 'Config Service' },
              { value: 'all', label: '全部' },
            ]} />
          </Form.Item>
        </Form>
      </Modal>
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
