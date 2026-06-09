import { useEffect, useState } from 'react'
import { Table, Tag, Button, Modal, Form, Input, Switch, InputNumber, message, Spin } from 'antd'
import { EditOutlined, DollarOutlined } from '@ant-design/icons'

interface Provider {
  name: string
  display_name: string
  config_schema: Record<string, any>
}

interface PlatformConfig {
  provider_name: string
  display_name: string
  enabled: string
  priority: number
  config: Record<string, any>
}

export default function SmsConfigPage() {
  const [providers, setProviders] = useState<Provider[]>([])
  const [configs, setConfigs] = useState<PlatformConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [editVisible, setEditVisible] = useState(false)
  const [editingProvider, setEditingProvider] = useState<string>('')
  const [balances, setBalances] = useState<Record<string, number>>({})
  const [form] = Form.useForm()

  useEffect(() => {
    Promise.all([
      fetch('/api/sms/providers').then(r => r.json()),
      fetch('/api/sms/config').then(r => r.json()),
    ]).then(([pRes, cRes]) => {
      setProviders(pRes.data || [])
      setConfigs(cRes.data || [])
    }).catch(() => message.error('加载失败'))
      .finally(() => setLoading(false))
  }, [])

  const checkBalance = async (name: string) => {
    try {
      const res = await fetch(`/api/sms/providers/${name}/balance`).then(r => r.json())
      setBalances(prev => ({ ...prev, [name]: res.data?.balance || 0 }))
    } catch { message.error('查询余额失败') }
  }

  const openEdit = (provider: Provider) => {
    const existing = configs.find(c => c.provider_name === provider.name)
    setEditingProvider(provider.name)
    form.setFieldsValue({
      display_name: existing?.display_name || provider.display_name,
      enabled: existing?.enabled !== 'false',
      priority: existing?.priority || 0,
      api_key: existing?.config?.api_key || '',
      base_url: existing?.config?.base_url || provider.config_schema?.base_url?.default || '',
    })
    setEditVisible(true)
  }

  const saveConfig = async () => {
    const values = await form.validateFields()
    await fetch(`/api/sms/config/${editingProvider}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        display_name: values.display_name,
        enabled: values.enabled ? 'true' : 'false',
        priority: values.priority,
        config: { api_key: values.api_key, base_url: values.base_url },
      }),
    })
    message.success('保存成功')
    setEditVisible(false)
    const cRes = await fetch('/api/sms/config').then(r => r.json())
    setConfigs(cRes.data || [])
  }

  const columns = [
    { title: '平台名称', dataIndex: 'name', key: 'name' },
    { title: '显示名', dataIndex: 'display_name', key: 'display_name' },
    {
      title: '状态', key: 'status',
      render: (_: any, record: Provider) => {
        const cfg = configs.find(c => c.provider_name === record.name)
        return cfg?.enabled === 'true' ? <Tag color="green">已启用</Tag> : <Tag>未配置</Tag>
      }
    },
    {
      title: '余额', key: 'balance',
      render: (_: any, record: Provider) => (
        <span>
          {balances[record.name] !== undefined ? `$${balances[record.name].toFixed(2)}` : '-'}
          <Button type="link" size="small" icon={<DollarOutlined />} onClick={() => checkBalance(record.name)}>查询</Button>
        </span>
      )
    },
    {
      title: '操作', key: 'action',
      render: (_: any, record: Provider) => (
        <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(record)}>配置</Button>
      )
    },
  ]

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>接码平台配置</h2>
      <Table rowKey="name" columns={columns} dataSource={providers} pagination={false} />

      <Modal title={`配置 ${editingProvider}`} open={editVisible} onOk={saveConfig} onCancel={() => setEditVisible(false)}>
        <Form form={form} layout="vertical">
          <Form.Item name="display_name" label="显示名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="api_key" label="API Key" rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="base_url" label="API Base URL">
            <Input />
          </Form.Item>
          <Form.Item name="priority" label="优先级">
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
