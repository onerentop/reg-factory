import { Card, Empty } from 'antd'

export default function SmsConfigPage() {
  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>接码平台配置</h2>
      <Card><Empty description="暂无接码平台配置" /></Card>
    </div>
  )
}
