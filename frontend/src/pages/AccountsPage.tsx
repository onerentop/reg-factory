import { useParams } from 'react-router-dom'
import { Table, Tag, Button, Space } from 'antd'

export default function AccountsPage() {
  const { platform } = useParams<{ platform: string }>()

  const columns = [
    { title: '邮箱', dataIndex: 'email', key: 'email' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (s: string) => <Tag color={s === 'success' ? 'green' : s === 'failed' ? 'red' : 'blue'}>{s}</Tag> },
    { title: '进度', dataIndex: 'progress', key: 'progress' },
    { title: '时间', dataIndex: 'created_at', key: 'created_at' },
    { title: '操作', key: 'action', render: () => <Space><Button size="small" type="link">详情</Button></Space> },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>{platform === 'outlook' ? 'Outlook' : 'Google'} 账户管理</h2>
      <Table columns={columns} dataSource={[]} pagination={{ pageSize: 20 }} />
    </div>
  )
}
