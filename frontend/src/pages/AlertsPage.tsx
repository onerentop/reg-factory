import { useEffect, useState } from 'react'
import { Table, Tag, Button, Modal, Form, Input, Select, Switch, Tabs, message } from 'antd'
import { PlusOutlined, BellOutlined } from '@ant-design/icons'

interface AlertRule {
  id: string
  name: string
  rule_type: string
  threshold: string | null
  enabled: boolean
  notify_channels: string[]
}

interface AlertEvent {
  id: string
  rule_name: string
  rule_type: string
  message: string
  resolved: boolean
  created_at: string
}

function RulesTab() {
  const [rules, setRules] = useState<AlertRule[]>([])
  const [addVisible, setAddVisible] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => {
    fetch('/api/alerts/rules').then(r => r.json())
      .then(res => setRules(res.data || []))
      .catch(() => {})
  }, [])

  const addRule = async () => {
    const values = await form.validateFields()
    await fetch('/api/alerts/rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(values),
    })
    message.success('规则已添加')
    setAddVisible(false)
    form.resetFields()
  }

  const columns = [
    { title: '规则名', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'rule_type', key: 'type', render: (t: string) => <Tag>{t}</Tag> },
    { title: '阈值', dataIndex: 'threshold', key: 'threshold', render: (v: string | null) => v || '-' },
    { title: '状态', dataIndex: 'enabled', key: 'enabled', render: (e: boolean) => <Tag color={e ? 'green' : 'default'}>{e ? '启用' : '禁用'}</Tag> },
    { title: '通知渠道', dataIndex: 'notify_channels', key: 'channels', render: (c: string[]) => c?.map(ch => <Tag key={ch}>{ch}</Tag>) || '-' },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddVisible(true)}>添加规则</Button>
      </div>
      <Table rowKey="id" columns={columns} dataSource={rules} pagination={false} />
      <Modal title="添加告警规则" open={addVisible} onOk={addRule} onCancel={() => setAddVisible(false)}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="规则名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="rule_type" label="规则类型" rules={[{ required: true }]}>
            <Select options={[
              { value: 'sms_balance', label: '接码余额不足' },
              { value: 'failure_rate', label: '注册失败率过高' },
              { value: 'service_down', label: '服务不可达' },
              { value: 'memory_high', label: '内存使用过高' },
            ]} />
          </Form.Item>
          <Form.Item name="threshold" label="阈值"><Input placeholder="例: 10 ($)" /></Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked" initialValue={true}><Switch /></Form.Item>
          <Form.Item name="notify_channels" label="通知渠道">
            <Select mode="multiple" options={[
              { value: 'web', label: '页面通知' },
              { value: 'email', label: '邮件' },
              { value: 'webhook', label: 'Webhook' },
            ]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

function HistoryTab() {
  const [events] = useState<AlertEvent[]>([])
  const columns = [
    { title: '时间', dataIndex: 'created_at', key: 'time', render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-' },
    { title: '规则', dataIndex: 'rule_name', key: 'rule' },
    { title: '类型', dataIndex: 'rule_type', key: 'type', render: (t: string) => <Tag>{t}</Tag> },
    { title: '消息', dataIndex: 'message', key: 'msg', ellipsis: true },
    { title: '状态', dataIndex: 'resolved', key: 'resolved', render: (r: boolean) => <Tag color={r ? 'green' : 'red'}>{r ? '已处理' : '未处理'}</Tag> },
  ]
  return <Table rowKey="id" columns={columns} dataSource={events} locale={{ emptyText: '暂无告警记录' }} />
}

export default function AlertsPage() {
  return (
    <div>
      <h2 style={{ marginBottom: 24 }}><BellOutlined /> 告警通知</h2>
      <Tabs items={[
        { key: 'rules', label: '告警规则', children: <RulesTab /> },
        { key: 'history', label: '告警历史', children: <HistoryTab /> },
      ]} />
    </div>
  )
}
