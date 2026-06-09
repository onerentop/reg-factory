import { useState } from 'react'
import { Table, Select, Input, Card, Space, Tag } from 'antd'
import { SearchOutlined } from '@ant-design/icons'

interface AuditEntry {
  operator: string
  action: string
  target: string | null
  before_value: any
  after_value: any
  ip_address: string | null
  created_at: string
}

const actionColors: Record<string, string> = {
  delete: 'red',
  create: 'green',
  update: 'blue',
  revoke: 'orange',
  login: 'cyan',
}

export default function AuditPage() {
  const [logs] = useState<AuditEntry[]>([])

  const columns = [
    { title: '时间', dataIndex: 'created_at', key: 'time', width: 170, render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-' },
    { title: '操作人', dataIndex: 'operator', key: 'operator', width: 120 },
    { title: '操作', dataIndex: 'action', key: 'action', width: 120, render: (a: string) => <Tag color={actionColors[a] || 'default'}>{a}</Tag> },
    { title: '目标', dataIndex: 'target', key: 'target', ellipsis: true },
    { title: 'IP', dataIndex: 'ip_address', key: 'ip', width: 130 },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>操作审计</h2>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input prefix={<SearchOutlined />} placeholder="操作人" style={{ width: 160 }} />
          <Select placeholder="操作类型" allowClear style={{ width: 140 }}
            options={[
              { value: 'create', label: '创建' },
              { value: 'update', label: '修改' },
              { value: 'delete', label: '删除' },
              { value: 'revoke', label: '撤销' },
              { value: 'login', label: '登录' },
            ]}
          />
        </Space>
      </Card>
      <Table rowKey="created_at" columns={columns} dataSource={logs} pagination={{ pageSize: 20, showTotal: t => `共 ${t} 条` }} locale={{ emptyText: '暂无审计记录' }} size="small" />
    </div>
  )
}
