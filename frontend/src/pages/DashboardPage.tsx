import { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic, Table, Tag, Spin, message } from 'antd'
import { wsClient } from '../websocket/WebSocketClient'
import {
  UserOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ThunderboltOutlined,
  DollarOutlined,
  ApiOutlined,
} from '@ant-design/icons'

interface DashboardData {
  accounts: { total: number; success?: number; failed?: number; running?: number }
  sms: { providers_count: number; total_balance?: number }
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [activities, setActivities] = useState<any[]>([])

  useEffect(() => {
    setLoading(true)
    fetch('/api/dashboard')
      .then((r) => r.json())
      .then((res) => setData(res.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    wsClient.connect()
    const unsubReg = wsClient.on('registration', (data: any) => {
      setActivities(prev => [{ key: Date.now().toString(), ...data }, ...prev].slice(0, 20))
    })
    const unsubAlert = wsClient.on('alert', (data: any) => {
      message.warning(data.message || '收到告警')
    })
    return () => { unsubReg(); unsubAlert() }
  }, [])

  const activityColumns = [
    { title: '邮箱', dataIndex: 'email', key: 'email' },
    { title: '平台', dataIndex: 'platform', key: 'platform' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => (
        <Tag color={s === 'success' ? 'green' : s === 'failed' ? 'red' : 'blue'}>
          {s}
        </Tag>
      ),
    },
    { title: '时间', dataIndex: 'created_at', key: 'created_at' },
  ]

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>仪表盘</h2>

      <Row gutter={[16, 16]}>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="总账户"
              value={data?.accounts?.total || 0}
              prefix={<UserOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="成功"
              value={data?.accounts?.success || 0}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: 'var(--success)' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="失败"
              value={data?.accounts?.failed || 0}
              prefix={<CloseCircleOutlined />}
              valueStyle={{ color: 'var(--error)' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="运行中"
              value={data?.accounts?.running || 0}
              prefix={<ThunderboltOutlined />}
              valueStyle={{ color: 'var(--accent)' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="接码平台"
              value={data?.sms?.providers_count || 0}
              prefix={<ApiOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="接码余额"
              value={data?.sms?.total_balance || 0}
              prefix={<DollarOutlined />}
              precision={2}
            />
          </Card>
        </Col>
      </Row>

      <Card title="最近注册活动" style={{ marginTop: 24 }}>
        <Table
          columns={activityColumns}
          dataSource={activities}
          pagination={false}
          size="small"
          locale={{ emptyText: '暂无活动' }}
        />
      </Card>
    </div>
  )
}
