import { useEffect, useState, useCallback, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { Table, Button, Space, Input, Select, Modal, message, Steps, Alert, InputNumber, Spin, Tooltip, Row, Col, Card, Statistic } from 'antd'
import {
  ReloadOutlined,
  DeleteOutlined,
  ExportOutlined,
  PlusOutlined,
  SearchOutlined,
  LoadingOutlined,
  CopyOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  ClockCircleFilled,
  KeyOutlined,
  SyncOutlined,
} from '@ant-design/icons'

interface Step {
  name: string
  status: string
  error_message?: string
  duration_ms?: number
}

interface Account {
  id: string
  email: string
  password?: string
  platform: string
  status: string
  current_step: number
  total_steps: number
  error_message?: string
  proxy_used?: string
  tokens?: { refresh_token?: string; client_id?: string }
  created_at?: string
  steps?: Step[]
}

const statusConfig: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  success: { color: 'green', icon: <CheckCircleFilled style={{ color: '#16a34a' }} />, label: '成功' },
  failed: { color: 'red', icon: <CloseCircleFilled style={{ color: '#dc2626' }} />, label: '失败' },
  running: { color: 'blue', icon: <SyncOutlined spin style={{ color: '#7c5cfc' }} />, label: '运行中' },
  pending: { color: 'default', icon: <ClockCircleFilled style={{ color: '#9f9bab' }} />, label: '等待中' },
}

export default function AccountsPage() {
  const { platform } = useParams<{ platform: string }>()
  const [accounts, setAccounts] = useState<Account[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [keyword, setKeyword] = useState('')
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])
  const [expandedRowKeys, setExpandedRowKeys] = useState<string[]>([])
  const [registerVisible, setRegisterVisible] = useState(false)
  const [registerCount, setRegisterCount] = useState(1)
  const [selectedProxy, setSelectedProxy] = useState<string>('')
  const [proxyList, setProxyList] = useState<any[]>([])
  const [registering, setRegistering] = useState(false)
  const [_taskId, setTaskId] = useState<string | null>(null)
  const [taskStatus, setTaskStatus] = useState<string>('')
  const [logLines, setLogLines] = useState<string[]>([])
  const logRef = useRef<HTMLDivElement>(null)

  const fetchAccounts = useCallback(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (platform) params.set('platform', platform)
    if (statusFilter) params.set('status', statusFilter)
    if (keyword) params.set('keyword', keyword)
    params.set('page', String(page))
    params.set('page_size', String(pageSize))

    fetch(`/api/accounts?${params}`)
      .then((r) => r.json())
      .then((res) => {
        const data = res.data || {}
        setAccounts(data.items || [])
        setTotal(data.total || 0)
      })
      .catch(() => message.error('加载失败'))
      .finally(() => setLoading(false))
  }, [platform, statusFilter, keyword, page, pageSize])

  useEffect(() => { fetchAccounts() }, [fetchAccounts])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logLines])

  const successCount = accounts.filter(a => a.status === 'success').length
  const failedCount = accounts.filter(a => a.status === 'failed').length
  const tokenCount = accounts.filter(a => a.tokens?.refresh_token).length

  const copyEmail = (email: string) => {
    navigator.clipboard.writeText(email)
    message.success({ content: '已复制', duration: 1 })
  }

  const extractToken = async (record: Account) => {
    message.loading({ content: '提取中...', key: 'ext' })
    try {
      const resp = await fetch('/api/tools/extract-graph-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account_id: record.id }),
      })
      const data = await resp.json()
      if (data.data?.success) {
        message.success({ content: 'Token 提取成功', key: 'ext' })
        fetchAccounts()
      } else {
        message.error({ content: `失败: ${data.data?.error || '未知'}`, key: 'ext' })
      }
    } catch {
      message.error({ content: '请求失败', key: 'ext' })
    }
  }

  const handleStartRegister = async () => {
    setRegistering(true)
    setTaskStatus('正在提交...')
    setLogLines([])
    try {
      const resp = await fetch('/api/register/outlook', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: registerCount, proxy: selectedProxy }),
      })
      const data = await resp.json()
      if (data.data?.task_id) {
        const tid = data.data.task_id
        setTaskId(tid)
        setTaskStatus('注册中...')
        setLogLines(prev => [...prev, `[任务] 已提交 (${tid.slice(0, 8)}...)`])
        const wsUrl = `ws://${window.location.hostname}:8000/ws/task/${tid}/logs`
        const ws = new WebSocket(wsUrl)
        ws.onmessage = (e) => {
          try {
            const d = JSON.parse(e.data)
            if (d.type === 'log' && d.message) setLogLines(prev => [...prev, d.message].slice(-200))
            if (d.type === 'done') ws.close()
          } catch { setLogLines(prev => [...prev, e.data]) }
        }
        const interval = setInterval(async () => {
          try {
            const r = await fetch(`/api/tasks/${tid}`)
            const d = await r.json()
            const s = d.data?.status
            if (s === 'SUCCESS') {
              clearInterval(interval)
              setRegistering(false)
              const results = d.data?.result?.results || []
              const ok = results.filter((r: any) => r.success).length
              if (ok > 0) {
                const emails = results.filter((r: any) => r.success).map((r: any) => r.email).join(', ')
                message.success(`注册成功: ${emails}`)
                setTaskStatus(`✅ ${emails}`)
                setLogLines(prev => [...prev, `🎉 成功: ${emails}`])
                fetchAccounts()
              } else {
                const err = results[0]?.steps?.find((s: any) => !s.success)?.error || '失败'
                message.error(`注册失败: ${err}`)
                setTaskStatus(`❌ ${err}`)
                setLogLines(prev => [...prev, `💥 ${err}`])
              }
            } else if (s === 'FAILURE') {
              clearInterval(interval)
              setRegistering(false)
              setTaskStatus('任务异常')
            }
          } catch {}
        }, 5000)
      } else {
        setRegistering(false)
        message.error('提交失败')
      }
    } catch {
      setRegistering(false)
      message.error('请求失败')
    }
  }

  const handleBatchDelete = () => {
    Modal.confirm({
      title: `确认删除 ${selectedRowKeys.length} 个账户？`,
      onOk: () =>
        fetch('/api/accounts/batch/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ account_ids: selectedRowKeys }),
        }).then(() => { message.success('已删除'); setSelectedRowKeys([]); fetchAccounts() }),
    })
  }

  const handleExport = (format: string) => {
    fetch('/api/accounts/batch/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_ids: selectedRowKeys.length > 0 ? selectedRowKeys : [], format, platform }),
    }).then(r => r.json()).then(res => {
      const blob = new Blob([res.data?.content || ''], { type: 'text/plain' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `accounts_${platform}_${Date.now()}.${format}`
      a.click()
      message.success('导出成功')
    })
  }

  const columns = [
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      render: (email: string) => (
        <Space size={4}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13 }}>{email}</span>
          <Tooltip title="复制"><CopyOutlined style={{ color: 'var(--text-muted)', cursor: 'pointer', fontSize: 12 }} onClick={() => copyEmail(email)} /></Tooltip>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (s: string) => {
        const cfg = statusConfig[s] || statusConfig.pending
        return <Space size={6}>{cfg.icon}<span style={{ fontSize: 13 }}>{cfg.label}</span></Space>
      },
    },
    {
      title: 'Token',
      key: 'token',
      width: 80,
      render: (_: any, record: Account) => {
        const hasToken = !!record.tokens?.refresh_token
        return hasToken
          ? <Tooltip title="已有 Token"><KeyOutlined style={{ color: 'var(--success)', fontSize: 15 }} /></Tooltip>
          : <Tooltip title="无 Token"><KeyOutlined style={{ color: 'var(--border-bright)', fontSize: 15 }} /></Tooltip>
      },
    },
    {
      title: '注册时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (t: string) => t ? (
        <span style={{ color: 'var(--text-secondary)', fontSize: 12.5, fontFamily: 'var(--font-mono)' }}>
          {new Date(t).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </span>
      ) : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 170,
      render: (_: any, record: Account) => (
        <Space size={0}>
          {record.status === 'success' && !record.tokens?.refresh_token && (
            <Button size="small" type="link" icon={<KeyOutlined />} onClick={() => extractToken(record)}>
              提取Token
            </Button>
          )}
          {record.status === 'failed' && (
            <Button size="small" type="link" icon={<ReloadOutlined />} onClick={() => {
              fetch('/api/accounts/batch/retry', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ account_ids: [record.id] }),
              }).then(() => message.success('已加入重试队列'))
            }}>重试</Button>
          )}
          <Button size="small" type="link" danger icon={<DeleteOutlined />} onClick={() => {
            Modal.confirm({
              title: '确认删除？',
              onOk: () => fetch(`/api/accounts/${record.id}`, { method: 'DELETE' })
                .then(() => { message.success('已删除'); fetchAccounts() }),
            })
          }}>删除</Button>
        </Space>
      ),
    },
  ]

  const expandedRowRender = (record: Account) => {
    const steps = record.steps || []
    if (steps.length === 0) return <div style={{ padding: 16, color: 'var(--text-muted)' }}>暂无步骤信息</div>
    const failedStep = steps.find(s => s.status === 'failed')
    return (
      <div style={{ padding: '12px 0' }}>
        <Steps size="small"
          current={steps.findIndex(s => s.status === 'failed') >= 0 ? steps.findIndex(s => s.status === 'failed') : steps.length}
          status={failedStep ? 'error' : 'finish'}
          items={steps.map(s => ({
            title: s.name,
            description: s.duration_ms ? `${s.duration_ms}ms` : undefined,
            status: s.status === 'success' ? 'finish' : s.status === 'failed' ? 'error' : s.status === 'running' ? 'process' : 'wait',
          }))}
        />
        {failedStep && (
          <Alert type="error" message={failedStep.error_message || '步骤执行失败'} style={{ marginTop: 12 }}
            action={<Button size="small" type="primary" danger>从此步重试</Button>}
          />
        )}
      </div>
    )
  }

  const platformTitle = platform === 'outlook' ? 'Outlook' : 'Google'

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2>{platformTitle} 账户管理</h2>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchAccounts}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => {
            fetch('/api/proxy').then(r => r.json()).then(res => {
              setProxyList((res.data || []).filter((p: any) => p.status === 'active' || p.status === 'available'))
            }).catch(() => {})
            setRegisterVisible(true)
          }}>新建注册</Button>
        </Space>
      </div>

      {/* Stats Cards */}
      <Row gutter={12} style={{ marginBottom: 20 }}>
        <Col span={6}>
          <Card size="small" style={{ borderLeft: '3px solid var(--accent)' }}>
            <Statistic title="总账户" value={total} valueStyle={{ fontSize: 24 }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ borderLeft: '3px solid var(--success)' }}>
            <Statistic title="注册成功" value={successCount} valueStyle={{ fontSize: 24, color: 'var(--success)' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ borderLeft: '3px solid var(--error)' }}>
            <Statistic title="注册失败" value={failedCount} valueStyle={{ fontSize: 24, color: 'var(--error)' }} />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" style={{ borderLeft: '3px solid var(--warning)' }}>
            <Statistic title="已有 Token" value={tokenCount} valueStyle={{ fontSize: 24, color: 'var(--warning)' }} suffix={<span style={{ fontSize: 13, color: 'var(--text-muted)' }}>/ {total}</span>} />
          </Card>
        </Col>
      </Row>

      {/* Toolbar */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexWrap: 'wrap', alignItems: 'center' }}>
        <Input
          prefix={<SearchOutlined style={{ color: 'var(--text-muted)' }} />}
          placeholder="搜索邮箱..."
          allowClear
          style={{ width: 240 }}
          onPressEnter={(e) => { setKeyword((e.target as HTMLInputElement).value); setPage(1) }}
          onChange={(e) => { if (!e.target.value) { setKeyword(''); setPage(1) } }}
        />
        <Select
          placeholder="状态"
          allowClear
          style={{ width: 120 }}
          onChange={(v) => { setStatusFilter(v); setPage(1) }}
          options={[
            { value: 'success', label: '✅ 成功' },
            { value: 'failed', label: '❌ 失败' },
            { value: 'running', label: '🔄 运行中' },
            { value: 'pending', label: '⏳ 等待' },
          ]}
        />
        <div style={{ flex: 1 }} />
        {selectedRowKeys.length > 0 && (
          <Space>
            <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>已选 {selectedRowKeys.length}</span>
            <Button size="small" icon={<ExportOutlined />} onClick={() => handleExport('txt')}>导出 TXT</Button>
            <Button size="small" icon={<ExportOutlined />} onClick={() => handleExport('csv')}>导出 CSV</Button>
            <Button size="small" danger icon={<DeleteOutlined />} onClick={handleBatchDelete}>批量删除</Button>
          </Space>
        )}
      </div>

      {/* Table */}
      <Table
        rowKey="id"
        columns={columns}
        dataSource={accounts}
        loading={loading}
        expandable={{
          expandedRowKeys,
          onExpand: (expanded, record) => setExpandedRowKeys(expanded ? [record.id] : []),
          expandedRowRender,
        }}
        rowSelection={{ selectedRowKeys, onChange: (keys) => setSelectedRowKeys(keys as string[]) }}
        pagination={{
          current: page, pageSize, total,
          showSizeChanger: true, pageSizeOptions: ['20', '50', '100'],
          showTotal: (t) => <span style={{ color: 'var(--text-muted)' }}>共 {t} 条</span>,
          onChange: (p, ps) => { setPage(p); setPageSize(ps) },
        }}
        size="middle"
      />

      {/* Register Modal */}
      <Modal
        title={<span style={{ fontWeight: 700 }}>新建 {platformTitle} 注册</span>}
        open={registerVisible}
        onCancel={() => { if (!registering) { setRegisterVisible(false); setLogLines([]) } }}
        footer={registering ? null : undefined}
        closable={!registering}
        maskClosable={!registering}
        width={720}
      >
        {!registering && logLines.length === 0 ? (
          <div style={{ padding: '8px 0' }}>
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', marginBottom: 6, fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>注册数量</label>
              <InputNumber min={1} max={20} value={registerCount} onChange={(v) => setRegisterCount(v || 1)} style={{ width: '100%' }} />
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', marginBottom: 6, fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)' }}>使用代理</label>
              <Select
                style={{ width: '100%' }}
                value={selectedProxy}
                onChange={setSelectedProxy}
                options={[
                  { value: '', label: '🎲 自动选择（从已激活代理中随机）' },
                  ...proxyList.map(p => ({
                    value: `${p.type}://${p.username}:${p.password}@${p.host}:${p.port}`,
                    label: `${p.host}:${p.port} — ${p.username?.match(/region-(\w+)/)?.[1] || p.type}`,
                  })),
                ]}
              />
              {proxyList.length === 0 && (
                <div style={{ color: 'var(--error)', fontSize: 12, marginTop: 6 }}>
                  没有已激活的代理，请先到代理配置页面添加
                </div>
              )}
            </div>
            <Button type="primary" block size="large" onClick={handleStartRegister} style={{ height: 44, fontSize: 15 }}>
              开始注册
            </Button>
          </div>
        ) : (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              {registering && <Spin indicator={<LoadingOutlined style={{ fontSize: 16 }} spin />} />}
              <span style={{ fontWeight: 600, color: registering ? 'var(--accent)' : 'var(--text-primary)', fontSize: 14 }}>
                {taskStatus}
              </span>
            </div>
            <div
              ref={logRef}
              style={{
                background: '#1c1917',
                color: '#d6d3d1',
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
                lineHeight: 1.7,
                padding: 14,
                borderRadius: 10,
                height: 380,
                overflowY: 'auto',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-all',
                border: '1px solid #292524',
              }}
            >
              {logLines.length === 0 ? (
                <span style={{ color: '#78716c' }}>等待日志...</span>
              ) : logLines.map((line, i) => (
                <div key={i} style={{
                  color: line.includes('OK') || line.includes('成功') || line.includes('🎉') ? '#4ade80' :
                         line.includes('error') || line.includes('失败') || line.includes('💥') || line.includes('Error') ? '#f87171' :
                         line.includes('WARN') || line.includes('⚠') ? '#fbbf24' : '#d6d3d1',
                }}>{line}</div>
              ))}
            </div>
            {!registering && (
              <div style={{ marginTop: 14, textAlign: 'right' }}>
                <Button onClick={() => { setRegisterVisible(false); setLogLines([]) }}>关闭</Button>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
