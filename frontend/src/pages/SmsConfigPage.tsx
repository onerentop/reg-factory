import { useEffect, useState } from 'react'
import { Table, Tag, Button, Modal, Form, Input, Switch, InputNumber, message, Spin, Card, Select } from 'antd'
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
  const [gmailCfg, setGmailCfg] = useState<{provider:string;country:string;max_price:string;fixed_price:boolean}>({ provider: 'hero_sms', country: '', max_price: '0.2', fixed_price: false })
  const [gmailPrices, setGmailPrices] = useState<{country:string;cost:number;count:number;country_name?:string}[]>([])

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

  useEffect(() => {
    fetch('/api/config/gmail_sms_config').then(r => r.json()).then(res => {
      if (res.data?.value) {
        setGmailCfg(res.data.value)
        // 复访时回填「国家」下拉，否则下拉为空看不到已存国家
        if (res.data.value.provider) loadPrices(res.data.value.provider)
      }
    }).catch(() => {})
  }, [])

  const loadPrices = (provider: string) => {
    fetch(`/api/sms/providers/${provider}/prices?service=go`).then(r => r.json())
      .then(res => setGmailPrices(res.data || [])).catch(() => setGmailPrices([]))
  }

  const saveGmailCfg = () => {
    fetch('/api/config/gmail_sms_config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: 'gmail_sms_config', value: gmailCfg }),
    }).then(r => r.json()).then(res => {
      if (res.success === false) message.error(res.message || '保存失败')
      else message.success('已保存')
    }).catch(() => message.error('保存失败'))
  }

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

      <Card title="Google 注册接码" style={{ marginTop: 16 }}>
        <Form layout="inline">
          <Form.Item label="平台">
            <Select style={{ width: 140 }} value={gmailCfg.provider}
              onChange={(v) => { setGmailCfg({ ...gmailCfg, provider: v }); loadPrices(v) }}
              options={providers.map(p => ({ value: p.name, label: p.display_name || p.name }))} />
          </Form.Item>
          <Form.Item label="国家">
            <Select style={{ width: 220 }} value={gmailCfg.country} showSearch
              onChange={(v) => { const row = gmailPrices.find(r => r.country === v); setGmailCfg({ ...gmailCfg, country: v, max_price: row ? String(row.cost) : gmailCfg.max_price }) }}
              options={gmailPrices.map(r => ({ value: r.country, label: `${r.country_name || r.country} / ${r.cost} / 库存${r.count}` }))} />
          </Form.Item>
          <Form.Item label="价格上限"><InputNumber min={0} step={0.1} value={Number(gmailCfg.max_price)} onChange={(v) => setGmailCfg({ ...gmailCfg, max_price: String(v ?? 0) })} /></Form.Item>
          <Form.Item label="固定价格"><Switch checked={gmailCfg.fixed_price} onChange={(v) => setGmailCfg({ ...gmailCfg, fixed_price: v })} /></Form.Item>
          <Button type="primary" onClick={saveGmailCfg}>保存</Button>
        </Form>
      </Card>

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
