import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { Table, Tag, Button, Space, Input, Select, Modal, message, Steps, Alert, InputNumber, Spin } from 'antd'
import {
  ReloadOutlined,
  DeleteOutlined,
  ExportOutlined,
  PlusOutlined,
  SearchOutlined,
  LoadingOutlined,
} from '@ant-design/icons'
import type { Account } from '../api/accounts'

const { Search } = Input

const statusColors: Record<string, string> = {
  success: 'green',
  failed: 'red',
  running: 'blue',
  pending: 'default',
  locked: 'orange',
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
  const [registering, setRegistering] = useState(false)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [taskStatus, setTaskStatus] = useState<string>('')

  const handleStartRegister = async () => {
    setRegistering(true)
    setTaskStatus('正在提交任务...')
    try {
      const resp = await fetch('/api/register/outlook', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count: registerCount }),
      })
      const data = await resp.json()
      if (data.data?.task_id) {
        setTaskId(data.data.task_id)
        setTaskStatus(`任务已提交 (${data.data.task_id.slice(0, 8)}...)，正在注册...`)
        pollTaskResult(data.data.task_id)
      } else {
        setRegistering(false)
        message.error('提交失败')
      }
    } catch {
      setRegistering(false)
      message.error('请求失败，检查 Gateway 是否运行')
    }
  }

  const pollTaskResult = (tid: string) => {
    const interval = setInterval(async () => {
      try {
        const resp = await fetch(`/api/tasks/${tid}`)
        const data = await resp.json()
        const status = data.data?.status || 'UNKNOWN'
        if (status === 'SUCCESS') {
          clearInterval(interval)
          setRegistering(false)
          setRegisterVisible(false)
          const result = data.data?.result || {}
          const results = result.results || []
          const successCount = results.filter((r: any) => r.success).length
          message.success(`注册完成！成功 ${successCount}/${results.length}`)
          if (successCount > 0) {
            const emails = results.filter((r: any) => r.success).map((r: any) => r.email).join(', ')
            setTaskStatus(`成功: ${emails}`)
          }
          fetchAccounts()
        } else if (status === 'FAILURE') {
          clearInterval(interval)
          setRegistering(false)
          message.error(`注册失败: ${data.data?.error || '未知错误'}`)
          setTaskStatus('失败')
        } else {
          setTaskStatus(`状态: ${status}...`)
        }
      } catch {
        // keep polling
      }
    }, 5000)
  }

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

  useEffect(() => {
    fetchAccounts()
  }, [fetchAccounts])

  const handleBatchDelete = () => {
    Modal.confirm({
      title: `确认删除 ${selectedRowKeys.length} 个账户？`,
      onOk: () =>
        fetch('/api/accounts/batch/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ account_ids: selectedRowKeys }),
        }).then(() => {
          message.success('删除成功')
          setSelectedRowKeys([])
          fetchAccounts()
        }),
    })
  }

  const handleExport = (format: string) => {
    fetch('/api/accounts/batch/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account_ids: selectedRowKeys.length > 0 ? selectedRowKeys : [],
        format,
        platform,
      }),
    })
      .then((r) => r.json())
      .then((res) => {
        const content = res.data?.content || ''
        const blob = new Blob([content], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `accounts_${platform}_${Date.now()}.${format}`
        a.click()
        URL.revokeObjectURL(url)
        message.success('导出成功')
      })
  }

  const handleBatchRetry = () => {
    fetch('/api/accounts/batch/retry', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_ids: selectedRowKeys }),
    })
      .then(() => {
        message.success('重试任务已加入队列')
        setSelectedRowKeys([])
      })
  }

  const columns = [
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: string) => <Tag color={statusColors[s] || 'default'}>{s}</Tag>,
    },
    {
      title: '进度',
      key: 'progress',
      width: 80,
      render: (_: any, record: Account) =>
        `${record.current_step}/${record.total_steps}`,
    },
    {
      title: '代理',
      dataIndex: 'proxy_used',
      key: 'proxy_used',
      width: 150,
      ellipsis: true,
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: any, record: Account) => (
        <Space>
          {record.status === 'failed' && (
            <Button size="small" type="link" onClick={() => handleBatchRetry()}>
              重试
            </Button>
          )}
          <Button size="small" type="link" danger onClick={() => {
            Modal.confirm({
              title: '确认删除？',
              onOk: () =>
                fetch(`/api/accounts/${record.id}`, { method: 'DELETE' })
                  .then(() => { message.success('已删除'); fetchAccounts() }),
            })
          }}>
            删除
          </Button>
        </Space>
      ),
    },
  ]

  const expandedRowRender = (record: Account) => {
    const steps = record.steps || []
    if (steps.length === 0) return <div style={{ padding: 16, color: 'var(--text-secondary)' }}>暂无步骤信息</div>

    const currentStep = steps.findIndex((s) => s.status === 'failed')
    const failedStep = steps.find((s) => s.status === 'failed')

    return (
      <div style={{ padding: '12px 0' }}>
        <Steps
          size="small"
          current={currentStep >= 0 ? currentStep : steps.length}
          status={failedStep ? 'error' : 'finish'}
          items={steps.map((s) => ({
            title: s.name,
            description: s.duration_ms ? `${s.duration_ms}ms` : undefined,
            status: s.status === 'success' ? 'finish' : s.status === 'failed' ? 'error' : s.status === 'running' ? 'process' : 'wait',
          }))}
        />
        {failedStep && (
          <Alert
            type="error"
            message={failedStep.error_message || '步骤执行失败'}
            style={{ marginTop: 12 }}
            action={
              <Space>
                <Button size="small" type="primary" danger>从此步重试</Button>
                <Button size="small">查看日志</Button>
              </Space>
            }
          />
        )}
      </div>
    )
  }

  const platformTitle = platform === 'outlook' ? 'Outlook' : 'Google'

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2>{platformTitle} 账户管理</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setRegisterVisible(true)}>新建注册</Button>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <Search
          placeholder="搜索邮箱"
          allowClear
          style={{ width: 260 }}
          prefix={<SearchOutlined />}
          onSearch={(v) => { setKeyword(v); setPage(1) }}
        />
        <Select
          placeholder="状态筛选"
          allowClear
          style={{ width: 140 }}
          onChange={(v) => { setStatusFilter(v); setPage(1) }}
          options={[
            { value: 'success', label: '成功' },
            { value: 'failed', label: '失败' },
            { value: 'running', label: '运行中' },
            { value: 'pending', label: '待处理' },
          ]}
        />
        {selectedRowKeys.length > 0 && (
          <Space>
            <span style={{ color: 'var(--text-secondary)' }}>已选 {selectedRowKeys.length} 项</span>
            <Button icon={<ReloadOutlined />} onClick={handleBatchRetry}>批量重试</Button>
            <Button icon={<ExportOutlined />} onClick={() => handleExport('txt')}>导出 TXT</Button>
            <Button icon={<ExportOutlined />} onClick={() => handleExport('csv')}>导出 CSV</Button>
            <Button danger icon={<DeleteOutlined />} onClick={handleBatchDelete}>批量删除</Button>
          </Space>
        )}
      </div>

      <Table
        rowKey="id"
        columns={columns}
        dataSource={accounts}
        loading={loading}
        expandable={{
          expandedRowKeys,
          onExpand: (expanded, record) =>
            setExpandedRowKeys(expanded ? [record.id] : []),
          expandedRowRender,
        }}
        rowSelection={{
          selectedRowKeys,
          onChange: (keys) => setSelectedRowKeys(keys as string[]),
        }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          pageSizeOptions: ['20', '50', '100'],
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps) },
        }}
        size="middle"
      />

      <Modal
        title="新建 Outlook 注册"
        open={registerVisible}
        onCancel={() => { if (!registering) setRegisterVisible(false) }}
        footer={null}
        closable={!registering}
        maskClosable={!registering}
      >
        {!registering ? (
          <div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', marginBottom: 8 }}>注册数量：</label>
              <InputNumber min={1} max={20} value={registerCount} onChange={(v) => setRegisterCount(v || 1)} style={{ width: '100%' }} />
            </div>
            <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginBottom: 16 }}>
              将自动生成邮箱、使用配置的代理，通过 ixBrowser 完成注册。
            </div>
            <Button type="primary" block onClick={handleStartRegister}>
              开始注册
            </Button>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '24px 0' }}>
            <Spin indicator={<LoadingOutlined style={{ fontSize: 36 }} spin />} />
            <div style={{ marginTop: 16, color: 'var(--text-secondary)' }}>{taskStatus}</div>
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
              注册过程需要 2-5 分钟，请勿关闭页面
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
