import { useState } from 'react'
import { Card, Upload, Select, Button, Table, message, Alert, Space, Tag } from 'antd'
import { UploadOutlined, ImportOutlined } from '@ant-design/icons'

interface PreviewItem {
  email: string
  password?: string
  has_token: boolean
}

export default function ImportPage() {
  const [platform, setPlatform] = useState('outlook')
  const [format, setFormat] = useState('txt')
  const [content, setContent] = useState('')
  const [preview, setPreview] = useState<PreviewItem[]>([])
  const [importing, setImporting] = useState(false)

  const handleFileUpload = (file: File) => {
    const reader = new FileReader()
    reader.onload = (e) => {
      const text = e.target?.result as string
      setContent(text)
      const lines = text.trim().split('\n').filter(Boolean)
      const items: PreviewItem[] = lines.slice(0, 10).map(line => {
        const parts = line.split('----')
        return { email: parts[0] || '', password: parts[1] || '', has_token: !!parts[2] }
      })
      setPreview(items)
    }
    reader.readAsText(file)
    return false
  }

  const doImport = async () => {
    if (!content) { message.warning('请先上传文件'); return }
    setImporting(true)
    try {
      const resp = await fetch('/api/accounts/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ platform, format, content }),
      })
      const data = await resp.json()
      message.success(`成功导入 ${data.data?.imported || 0} 个账户`)
      setContent('')
      setPreview([])
    } catch { message.error('导入失败') }
    finally { setImporting(false) }
  }

  const previewColumns = [
    { title: '邮箱', dataIndex: 'email', key: 'email' },
    { title: '密码', dataIndex: 'password', key: 'password', render: (v: string) => v ? '***' : '-' },
    { title: 'Token', dataIndex: 'has_token', key: 'token', render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '有' : '无'}</Tag> },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}><ImportOutlined /> 数据导入</h2>
      <Card>
        <Space style={{ marginBottom: 16 }} wrap>
          <Select value={platform} onChange={setPlatform} style={{ width: 140 }}
            options={[{ value: 'outlook', label: 'Outlook' }, { value: 'google', label: 'Google' }]} />
          <Select value={format} onChange={setFormat} style={{ width: 120 }}
            options={[{ value: 'txt', label: 'TXT 格式' }, { value: 'json', label: 'JSON 格式' }]} />
          <Upload beforeUpload={handleFileUpload} showUploadList={false} accept=".txt,.json">
            <Button icon={<UploadOutlined />}>选择文件</Button>
          </Upload>
          <Button type="primary" icon={<ImportOutlined />} onClick={doImport} loading={importing} disabled={!content}>
            确认导入
          </Button>
        </Space>

        {format === 'txt' && (
          <Alert type="info" message="TXT 格式：每行一个账户，字段用 ---- 分隔（email----password----refresh_token----client_id）" style={{ marginBottom: 16 }} />
        )}

        {preview.length > 0 && (
          <div>
            <h4>预览（前 10 条）</h4>
            <Table rowKey="email" columns={previewColumns} dataSource={preview} pagination={false} size="small" />
            <p style={{ color: 'var(--text-secondary)', marginTop: 8 }}>
              共解析 {content.trim().split('\n').filter(Boolean).length} 行
            </p>
          </div>
        )}
      </Card>
    </div>
  )
}
