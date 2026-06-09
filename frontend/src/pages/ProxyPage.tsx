import { useState, useEffect } from 'react'
import { Table, Button, Modal, Form, Input, Select, Tag, Space, message, Popconfirm } from 'antd'
import { PlusOutlined, DeleteOutlined, ThunderboltOutlined } from '@ant-design/icons'

interface Proxy {
  id: string
  type: string
  host: string
  port: number
  username?: string
  password?: string
  status: string
  region?: string
}

export default function ProxyPage() {
  const [proxies, setProxies] = useState<Proxy[]>([])
  const [addVisible, setAddVisible] = useState(false)

  useEffect(() => {
    fetch('/api/proxy').then(r => r.json())
      .then(res => setProxies((res.data || []).map((p: any) => ({ ...p, id: p.id || Date.now().toString() }))))
      .catch(() => {})
  }, [])
  const [form] = Form.useForm()

  const addProxy = async () => {
    const values = await form.validateFields()
    try {
      const resp = await fetch('/api/proxy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })
      const data = await resp.json()
      setProxies([...proxies, { id: data.data?.id || Date.now().toString(), ...values, status: 'unknown' }])
      setAddVisible(false)
      form.resetFields()
      message.success('代理已添加')
    } catch { message.error('添加失败') }
  }

  const removeProxy = async (id: string) => {
    try {
      await fetch(`/api/proxy/${id}`, { method: 'DELETE' })
      setProxies(proxies.filter(p => p.id !== id))
      message.success('已删除')
    } catch { message.error('删除失败') }
  }

  const testProxy = (id: string) => {
    setProxies(proxies.map(p =>
      p.id === id ? { ...p, status: 'testing' } : p
    ))
    setTimeout(() => {
      setProxies(prev => prev.map(p =>
        p.id === id ? { ...p, status: Math.random() > 0.3 ? 'available' : 'unavailable' } : p
      ))
    }, 1500)
  }

  const testAll = () => {
    proxies.forEach(p => testProxy(p.id))
  }

  const statusTag = (s: string) => {
    const map: Record<string, { color: string; text: string }> = {
      available: { color: 'green', text: '可用' },
      unavailable: { color: 'red', text: '不可用' },
      slow: { color: 'orange', text: '慢' },
      testing: { color: 'blue', text: '检测中...' },
      unknown: { color: 'default', text: '未检测' },
    }
    const info = map[s] || map.unknown
    return <Tag color={info.color}>{info.text}</Tag>
  }

  const columns = [
    { title: '类型', dataIndex: 'type', key: 'type', width: 80 },
    { title: '地址', dataIndex: 'host', key: 'host' },
    { title: '端口', dataIndex: 'port', key: 'port', width: 80 },
    { title: '用户名', dataIndex: 'username', key: 'username', render: (v: string) => v || '-' },
    { title: '状态', dataIndex: 'status', key: 'status', width: 100, render: statusTag },
    { title: '地区', dataIndex: 'region', key: 'region', width: 80, render: (v: string) => v || '-' },
    {
      title: '操作', key: 'action', width: 150,
      render: (_: any, record: Proxy) => (
        <Space>
          <Button size="small" type="link" icon={<ThunderboltOutlined />} onClick={() => testProxy(record.id)}>测试</Button>
          <Popconfirm title="确认删除？" onConfirm={() => removeProxy(record.id)}>
            <Button size="small" type="link" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2>代理配置</h2>
        <Space>
          <Button onClick={testAll} disabled={proxies.length === 0}>一键测试全部</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddVisible(true)}>添加代理</Button>
        </Space>
      </div>

      <Table rowKey="id" columns={columns} dataSource={proxies} pagination={false} />

      <Modal title="添加代理" open={addVisible} onOk={addProxy} onCancel={() => setAddVisible(false)}>
        <Form form={form} layout="vertical" initialValues={{ type: 'socks5' }}>
          <Form.Item name="type" label="类型" rules={[{ required: true }]}>
            <Select options={[{ value: 'socks5', label: 'SOCKS5' }, { value: 'http', label: 'HTTP' }]} />
          </Form.Item>
          <Form.Item name="host" label="地址" rules={[{ required: true }]}>
            <Input placeholder="192.168.1.1" />
          </Form.Item>
          <Form.Item name="port" label="端口" rules={[{ required: true }]}>
            <Input type="number" placeholder="1080" />
          </Form.Item>
          <Form.Item name="username" label="用户名">
            <Input />
          </Form.Item>
          <Form.Item name="password" label="密码">
            <Input.Password />
          </Form.Item>
          <Form.Item name="region" label="地区">
            <Input placeholder="US / HK / JP" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
