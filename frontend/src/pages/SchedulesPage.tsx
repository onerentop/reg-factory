import { useState } from 'react'
import { Table, Button, Tag, Switch, Modal, Form, Input, Select, InputNumber, message, Space } from 'antd'
import { PlusOutlined, PlayCircleOutlined, ClockCircleOutlined } from '@ant-design/icons'

interface ScheduleTask {
  id: string
  name: string
  type: string
  cron: string
  enabled: boolean
  last_run: string | null
}

export default function SchedulesPage() {
  const [tasks, setTasks] = useState<ScheduleTask[]>([
    { id: '1', name: '代理健康检查', type: 'proxy_health', cron: '*/5 * * * *', enabled: true, last_run: null },
    { id: '2', name: '接码余额检查', type: 'sms_balance', cron: '*/10 * * * *', enabled: true, last_run: null },
    { id: '3', name: '日志清理', type: 'log_cleanup', cron: '0 2 * * *', enabled: false, last_run: null },
  ])
  const [addVisible, setAddVisible] = useState(false)
  const [form] = Form.useForm()

  const toggleEnable = (id: string) => {
    setTasks(tasks.map(t => t.id === id ? { ...t, enabled: !t.enabled } : t))
  }

  const addTask = async () => {
    const values = await form.validateFields()
    setTasks([...tasks, { id: Date.now().toString(), ...values, enabled: true, last_run: null }])
    setAddVisible(false)
    form.resetFields()
    message.success('任务已添加')
  }

  const columns = [
    { title: '任务名', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'type', key: 'type', render: (t: string) => <Tag>{t}</Tag> },
    { title: 'Cron 表达式', dataIndex: 'cron', key: 'cron', render: (c: string) => <code>{c}</code> },
    { title: '启用', key: 'enabled', render: (_: any, record: ScheduleTask) => <Switch checked={record.enabled} onChange={() => toggleEnable(record.id)} /> },
    { title: '上次运行', dataIndex: 'last_run', key: 'last_run', render: (t: string | null) => t || '从未' },
    { title: '操作', key: 'action', render: (_: any, record: ScheduleTask) => (
      <Button size="small" type="link" icon={<PlayCircleOutlined />}>立即执行</Button>
    )},
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2><ClockCircleOutlined /> 定时任务</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddVisible(true)}>添加任务</Button>
      </div>
      <Table rowKey="id" columns={columns} dataSource={tasks} pagination={false} />
      <Modal title="添加定时任务" open={addVisible} onOk={addTask} onCancel={() => setAddVisible(false)}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="任务名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="type" label="类型" rules={[{ required: true }]}>
            <Select options={[
              { value: 'register_batch', label: '计划注册' },
              { value: 'proxy_health', label: '代理健康检查' },
              { value: 'sms_balance', label: '接码余额检查' },
              { value: 'log_cleanup', label: '日志清理' },
            ]} />
          </Form.Item>
          <Form.Item name="cron" label="Cron 表达式" rules={[{ required: true }]}><Input placeholder="*/5 * * * *" /></Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
