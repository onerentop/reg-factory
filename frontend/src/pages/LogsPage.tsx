import { useState, useEffect, useCallback } from 'react'
import { Table, Select, DatePicker, Input, Tag, Space, Button, Card } from 'antd'
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons'
import type { Dayjs } from 'dayjs'

const { RangePicker } = DatePicker

interface LogEntry {
  id: string
  service: string
  level: string
  message: string
  trace_id: string
  account_id: string
  created_at: string
}

const levelColors: Record<string, string> = {
  DEBUG: 'default',
  INFO: 'blue',
  WARN: 'orange',
  WARNING: 'orange',
  ERROR: 'red',
}

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [service, setService] = useState<string>()
  const [level, setLevel] = useState<string>()
  const [keyword, setKeyword] = useState('')
  const [_dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>(null)

  const fetchLogs = useCallback(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (service) params.set('service', service)
    if (level) params.set('level', level)
    if (keyword) params.set('keyword', keyword)
    fetch(`/api/logs?${params}`)
      .then(r => r.json())
      .then(res => {
        const data = res.data || {}
        setLogs((data.items || []).map((item: any, idx: number) => ({ ...item, id: item.id || String(idx) })))
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [service, level, keyword])

  useEffect(() => { fetchLogs() }, [fetchLogs])

  const columns = [
    {
      title: '时间', dataIndex: 'created_at', key: 'time', width: 170,
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    { title: '服务', dataIndex: 'service', key: 'service', width: 120 },
    {
      title: '级别', dataIndex: 'level', key: 'level', width: 80,
      render: (l: string) => <Tag color={levelColors[l] || 'default'}>{l}</Tag>,
    },
    { title: '消息', dataIndex: 'message', key: 'message', ellipsis: true },
    {
      title: 'Trace ID', dataIndex: 'trace_id', key: 'trace_id', width: 120,
      render: (t: string) => t ? <code style={{ fontSize: 11 }}>{t.slice(0, 8)}...</code> : '-',
    },
  ]

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>日志查询</h2>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select placeholder="服务" allowClear style={{ width: 150 }} onChange={setService}
            options={[
              { value: 'gateway', label: 'Gateway' },
              { value: 'sms_service', label: 'SMS Service' },
              { value: 'account_service', label: 'Account Service' },
              { value: 'config_service', label: 'Config Service' },
              { value: 'worker', label: 'Worker' },
            ]}
          />
          <Select placeholder="级别" allowClear style={{ width: 120 }} onChange={setLevel}
            options={[
              { value: 'DEBUG', label: 'DEBUG' },
              { value: 'INFO', label: 'INFO' },
              { value: 'WARN', label: 'WARN' },
              { value: 'ERROR', label: 'ERROR' },
            ]}
          />
          <RangePicker showTime onChange={(dates) => setDateRange(dates as [Dayjs, Dayjs] | null)} />
          <Input prefix={<SearchOutlined />} placeholder="关键词搜索" style={{ width: 200 }}
            value={keyword} onChange={e => setKeyword(e.target.value)}
          />
          <Button icon={<ReloadOutlined />} onClick={fetchLogs}>刷新</Button>
        </Space>
      </Card>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={logs}
        loading={loading}
        pagination={{ pageSize: 50, showTotal: t => `共 ${t} 条` }}
        size="small"
        locale={{ emptyText: '暂无日志记录' }}
      />
    </div>
  )
}
