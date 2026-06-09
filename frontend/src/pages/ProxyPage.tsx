import { Card, Empty } from 'antd'

export default function ProxyPage() {
  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>代理配置</h2>
      <Card><Empty description="暂无代理配置" /></Card>
    </div>
  )
}
