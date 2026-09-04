import { useState, useEffect } from 'react'
import { Table, Button, Modal, Form, Input, Select, Tag, Space, message, Popconfirm, Switch, Tooltip } from 'antd'
import { PlusOutlined, DeleteOutlined, ThunderboltOutlined, EditOutlined, SearchOutlined, GlobalOutlined } from '@ant-design/icons'

interface Proxy {
  id: string
  type: string
  host: string
  port: number
  username?: string
  has_password?: boolean
  status: string
  active: boolean
  region?: string
  ip?: string
  today_bound?: number
  total_bound?: number
  today_profile_name?: string | null
  available_today?: boolean
}

export default function ProxyPage() {
  const [proxies, setProxies] = useState<Proxy[]>([])
  const [addVisible, setAddVisible] = useState(false)
  const [editVisible, setEditVisible] = useState(false)
  const [editingProxy, setEditingProxy] = useState<Proxy | null>(null)
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])
  const [searchText, setSearchText] = useState('')
  const [importVisible, setImportVisible] = useState(false)
  const [importText, setImportText] = useState('')
  const [importType, setImportType] = useState('http')
  const [bindings, setBindings] = useState<Record<string, any[]>>({})
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()

  const parseResponse = async (response: Response) => {
    const data = await response.json()
    if (!response.ok || data.success === false) {
      throw new Error(data.detail || data.message || '请求失败')
    }
    return data
  }

  const fetchProxies = () => {
    fetch('/api/proxy').then(parseResponse)
      .then(res => setProxies((res.data || []).map((p: any) => ({
        ...p,
        id: p.id || Date.now().toString(),
        active: p.status !== 'inactive',
      }))))
      .catch(() => {})
  }

  useEffect(() => { fetchProxies() }, [])

  const filteredProxies = proxies.filter(p => {
    if (!searchText) return true
    const s = searchText.toLowerCase()
    return (
      p.host.toLowerCase().includes(s) ||
      (p.username || '').toLowerCase().includes(s) ||
      (p.region || '').toLowerCase().includes(s) ||
      (p.ip || '').includes(s) ||
      p.type.toLowerCase().includes(s)
    )
  })

  const addProxy = async () => {
    const values = await form.validateFields()
    try {
      const resp = await fetch('/api/proxy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...values, status: 'active' }),
      })
      await parseResponse(resp)
      fetchProxies()
      setAddVisible(false)
      form.resetFields()
      message.success('代理已添加')
    } catch { message.error('添加失败') }
  }

  const importProxies = async () => {
    if (!importText.trim()) {
      message.warning('请粘贴代理列表')
      return
    }
    try {
      const resp = await fetch('/api/proxy/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: importText, type: importType, skip_duplicates: true }),
      })
      const data = await parseResponse(resp)
      const { imported, duplicates, invalid } = data.data
      message.success(`导入 ${imported} 条，跳过重复 ${duplicates} 条，非法 ${invalid.length} 行`)
      setImportVisible(false)
      setImportText('')
      fetchProxies()
    } catch { message.error('导入失败') }
  }

  const loadBindings = async (id: string) => {
    try {
      const resp = await fetch(`/api/proxy/${id}/bindings`)
      const data = await parseResponse(resp)
      setBindings(prev => ({ ...prev, [id]: data.data || [] }))
    } catch { setBindings(prev => ({ ...prev, [id]: [] })) }
  }

  const removeProxy = async (id: string) => {
    try {
      const response = await fetch(`/api/proxy/${id}`, { method: 'DELETE' })
      await parseResponse(response)
      setProxies(proxies.filter(p => p.id !== id))
      setSelectedRowKeys(selectedRowKeys.filter(k => k !== id))
      message.success('已删除')
    } catch { message.error('删除失败') }
  }

  const batchDelete = () => {
    Modal.confirm({
      title: `确认删除 ${selectedRowKeys.length} 个代理？`,
      onOk: async () => {
        await Promise.all(selectedRowKeys.map(async (id) => {
          const response = await fetch(`/api/proxy/${id}`, { method: 'DELETE' })
          await parseResponse(response)
        }))
        setSelectedRowKeys([])
        fetchProxies()
        message.success('批量删除完成')
      },
    })
  }

  const openEdit = (record: Proxy) => {
    setEditingProxy(record)
    editForm.setFieldsValue({
      type: record.type,
      host: record.host,
      port: record.port,
      username: record.username || '',
      password: '',
    })
    setEditVisible(true)
  }

  const saveEdit = async () => {
    if (!editingProxy) return
    const values = await editForm.validateFields()
    const payload = { ...values }
    if (!payload.password) delete payload.password
    try {
      const response = await fetch(`/api/proxy/${editingProxy.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      await parseResponse(response)
      setEditVisible(false)
      fetchProxies()
      message.success('已更新')
    } catch { message.error('更新失败') }
  }

  const toggleActive = async (id: string, active: boolean) => {
    try {
      const response = await fetch(`/api/proxy/${id}/status`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: active ? 'active' : 'inactive' }),
      })
      await parseResponse(response)
      setProxies(proxies.map(p => p.id === id ? { ...p, active, status: active ? 'active' : 'inactive' } : p))
    } catch { message.error('更新失败') }
  }

  const testProxy = async (id: string) => {
    setProxies(prev => prev.map(p => p.id === id ? { ...p, status: 'testing' } : p))
    try {
      const resp = await fetch(`/api/proxy/${id}/test`, { method: 'POST' })
      const data = await parseResponse(resp)
      const testResult = data.data?.result || 'unavailable'
      const ip = data.data?.ip || ''
      const region = data.data?.region || ''
      setProxies(prev => prev.map(p =>
        p.id === id ? {
          ...p,
          status: testResult === 'available' ? 'available' : testResult === 'slow' ? 'slow' : 'unavailable',
          ip, region,
        } : p
      ))
      if (testResult === 'available' || testResult === 'slow') {
        message.success(`代理可用 ${ip ? `(${ip})` : ''} ${region ? `[${region}]` : ''}`)
      } else {
        message.error('代理不可用')
      }
    } catch {
      setProxies(prev => prev.map(p => p.id === id ? { ...p, status: 'unavailable' } : p))
      message.error('测试失败')
    }
  }

  const testAll = () => { proxies.forEach(p => testProxy(p.id)) }

  const statusTag = (s: string) => {
    const map: Record<string, { color: string; text: string }> = {
      active: { color: 'green', text: '已激活' },
      available: { color: 'cyan', text: '可用' },
      inactive: { color: 'default', text: '未激活' },
      unavailable: { color: 'red', text: '不可用' },
      slow: { color: 'orange', text: '慢' },
      testing: { color: 'blue', text: '检测中...' },
      unknown: { color: 'default', text: '未检测' },
    }
    const info = map[s] || map.unknown
    return <Tag color={info.color}>{info.text}</Tag>
  }

  const columns = [
    { title: '类型', dataIndex: 'type', key: 'type', width: 80, render: (t: string) => <Tag>{t}</Tag> },
    { title: '地址', dataIndex: 'host', key: 'host' },
    { title: '端口', dataIndex: 'port', key: 'port', width: 70 },
    { title: '用户名', dataIndex: 'username', key: 'username', ellipsis: true, width: 200, render: (v: string) => v || '-' },
    {
      title: '出口IP / 地区', key: 'region', width: 160,
      render: (_: any, record: Proxy) => {
        if (record.ip || record.region) {
          return (
            <Tooltip title={record.ip || ''}>
              <Space size={4}>
                <GlobalOutlined style={{ color: 'var(--accent)' }} />
                <span>{record.region || record.ip || '-'}</span>
              </Space>
            </Tooltip>
          )
        }
        return <span style={{ color: 'var(--text-secondary)' }}>未检测</span>
      },
    },
    {
      title: '今日 / 累计', key: 'binding', width: 150,
      render: (_: any, record: Proxy) => (
        <Space size={4}>
          <Tag color={record.today_bound ? 'red' : 'green'}>
            今日 {record.today_bound ?? 0}/1
          </Tag>
          <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
            累计 {record.total_bound ?? 0}
          </span>
        </Space>
      ),
    },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: statusTag },
    {
      title: '激活', key: 'active', width: 60,
      render: (_: any, record: Proxy) => (
        <Switch size="small" checked={record.active !== false} onChange={(c) => toggleActive(record.id, c)} />
      ),
    },
    {
      title: '操作', key: 'action', width: 180,
      render: (_: any, record: Proxy) => (
        <Space size={0}>
          <Button size="small" type="link" icon={<ThunderboltOutlined />} onClick={() => testProxy(record.id)}>测试</Button>
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
          <Popconfirm title="确认删除？" onConfirm={() => removeProxy(record.id)}>
            <Button size="small" type="link" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const proxyFormFields = (
    <>
      <Form.Item name="type" label="类型" rules={[{ required: true }]}>
        <Select options={[{ value: 'socks5', label: 'SOCKS5' }, { value: 'http', label: 'HTTP' }]} />
      </Form.Item>
      <Form.Item name="host" label="地址" rules={[{ required: true }]}>
        <Input placeholder="hk.1024proxy.io" />
      </Form.Item>
      <Form.Item name="port" label="端口" rules={[{ required: true }]}>
        <Input type="number" placeholder="3000" />
      </Form.Item>
      <Form.Item name="username" label="用户名">
        <Input placeholder="sb7f3017-region-JP-sid-xxx" />
      </Form.Item>
      <Form.Item name="password" label="密码">
        <Input.Password />
      </Form.Item>
    </>
  )

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2>代理配置</h2>
        <Space>
          <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
            已激活 {proxies.filter(p => p.active !== false).length} / {proxies.length}
            ｜今日可用 {proxies.filter(p => p.available_today !== false).length} / {proxies.length}
          </span>
          <Input
            prefix={<SearchOutlined />}
            placeholder="搜索地址/用户名/地区"
            allowClear
            style={{ width: 220 }}
            onChange={e => setSearchText(e.target.value)}
          />
          {selectedRowKeys.length > 0 && (
            <Button danger icon={<DeleteOutlined />} onClick={batchDelete}>
              批量删除 ({selectedRowKeys.length})
            </Button>
          )}
          <Button onClick={testAll} disabled={proxies.length === 0}>一键测试</Button>
          <Button onClick={() => setImportVisible(true)}>批量导入</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddVisible(true)}>添加代理</Button>
        </Space>
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={filteredProxies}
        pagination={false}
        rowSelection={{
          selectedRowKeys,
          onChange: (keys) => setSelectedRowKeys(keys as string[]),
        }}
        expandable={{
          onExpand: (expanded, record) => { if (expanded) loadBindings(record.id) },
          expandedRowRender: (record: Proxy) => (
            <Table
              rowKey={(r: any) => `${r.bound_date}-${r.profile_id}`}
              size="small"
              pagination={false}
              locale={{ emptyText: '暂无绑定记录' }}
              dataSource={bindings[record.id] || []}
              columns={[
                { title: '日期', dataIndex: 'bound_date', key: 'bound_date' },
                { title: '窗口 ID', dataIndex: 'profile_id', key: 'profile_id',
                  render: (v: string) => v || '-' },
                { title: '窗口名 / 邮箱', dataIndex: 'profile_name', key: 'profile_name',
                  render: (v: string) => v || '-' },
                { title: '平台', dataIndex: 'platform', key: 'platform' },
                { title: '结果', dataIndex: 'status', key: 'status' },
              ]}
            />
          ),
        }}
        size="middle"
      />

      <Modal title="添加代理" open={addVisible} onOk={addProxy} onCancel={() => setAddVisible(false)}>
        <Form form={form} layout="vertical" initialValues={{ type: 'socks5' }}>
          {proxyFormFields}
        </Form>
      </Modal>

      <Modal title="编辑代理" open={editVisible} onOk={saveEdit} onCancel={() => setEditVisible(false)}>
        <Form form={editForm} layout="vertical">
          {proxyFormFields}
        </Form>
      </Modal>

      <Modal title="批量导入代理" open={importVisible} onOk={importProxies}
             onCancel={() => setImportVisible(false)} width={640}>
        <Select
          value={importType}
          onChange={setImportType}
          style={{ width: 160, marginBottom: 12 }}
          options={[{ value: 'http', label: 'HTTP' }, { value: 'socks5', label: 'SOCKS5' }]}
        />
        <Input.TextArea
          rows={12}
          value={importText}
          onChange={e => setImportText(e.target.value)}
          placeholder={'每行一条，支持：\nhost:port:user:pass\nuser:pass@host:port\nhost:port'}
        />
      </Modal>
    </div>
  )
}
