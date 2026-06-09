import { Card, Empty } from 'antd'

export default function LogsPage() {
  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>日志查询</h2>
      <Card><Empty description="暂无日志" /></Card>
    </div>
  )
}
