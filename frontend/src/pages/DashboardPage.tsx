import { Card, Row, Col, Statistic } from 'antd'
import { UserOutlined, CheckCircleOutlined, CloseCircleOutlined, ThunderboltOutlined } from '@ant-design/icons'

export default function DashboardPage() {
  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>仪表盘</h2>
      <Row gutter={16}>
        <Col span={6}>
          <Card><Statistic title="总账户" value={0} prefix={<UserOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="成功" value={0} prefix={<CheckCircleOutlined />} valueStyle={{ color: 'var(--success)' }} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="失败" value={0} prefix={<CloseCircleOutlined />} valueStyle={{ color: 'var(--error)' }} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="运行中" value={0} prefix={<ThunderboltOutlined />} valueStyle={{ color: 'var(--accent)' }} /></Card>
        </Col>
      </Row>
    </div>
  )
}
