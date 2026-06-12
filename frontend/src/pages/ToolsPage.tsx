import { useState } from 'react'
import { Card, Form, Input, InputNumber, Button, Select, message, Row, Col, Typography, Tag } from 'antd'
import { toolsApi } from '@/api/tools'

const { Title } = Typography
const PLATFORMS = ['claude', 'chatgpt', 'grok']

export default function ToolsPage() {
  const [results, setResults] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState<Record<string, boolean>>({})

  const run = async (key: string, fn: () => Promise<unknown>) => {
    setLoading((s) => ({ ...s, [key]: true }))
    try {
      const res = (await fn()) as { success?: boolean; message?: string; data?: { task_id?: string } }
      if (res?.success === false) {
        message.error(res?.message || '执行失败')
        setResults((s) => ({ ...s, [key]: '失败: ' + (res?.message || '') }))
        return
      }
      const taskId = res?.data?.task_id
      const txt = taskId ? `已触发，task: ${taskId}` : (res?.message || '已执行')
      message.success(txt)
      setResults((s) => ({ ...s, [key]: txt }))
    } catch (e) {
      const m = (e as { detail?: string; message?: string })?.detail || (e as Error)?.message || String(e)
      message.error('执行失败: ' + m)
      setResults((s) => ({ ...s, [key]: '失败: ' + m }))
    } finally {
      setLoading((s) => ({ ...s, [key]: false }))
    }
  }

  const result = (key: string) =>
    results[key] ? <Tag color="blue" style={{ marginTop: 8, whiteSpace: 'normal' }}>{results[key]}</Tag> : null

  return (
    <div style={{ padding: 24 }}>
      <Title level={2}>工具 / 运维</Title>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="解锁 Outlook 账号">
            <Form layout="vertical" onFinish={(v) => run('unlock', () => toolsApi.unlockOutlook(v.email, v.password))}>
              <Form.Item name="email" label="邮箱" rules={[{ required: true }]}><Input placeholder="xxx@outlook.com" /></Form.Item>
              <Form.Item name="password" label="密码" rules={[{ required: true }]}><Input.Password /></Form.Item>
              <Button type="primary" htmlType="submit" loading={loading.unlock}>执行</Button>
              {result('unlock')}
            </Form>
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title="校验 Session Key">
            <Form layout="vertical" onFinish={(v) => run('validate', () => toolsApi.validateKey(v.key))}>
              <Form.Item name="key" label="Key" rules={[{ required: true }]}><Input.TextArea rows={2} placeholder="refresh_token / session key" /></Form.Item>
              <Button type="primary" htmlType="submit" loading={loading.validate}>执行</Button>
              {result('validate')}
            </Form>
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title="激活 ChatGPT Plus">
            <Form layout="vertical" onFinish={(v) => run('plus', () => toolsApi.activatePlus(v.access_token, v.email, v.card))}>
              <Form.Item name="access_token" label="Access Token" rules={[{ required: true }]}><Input.TextArea rows={2} /></Form.Item>
              <Form.Item name="email" label="邮箱" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item name="card" label="卡(选填)"><Input placeholder="可留空" /></Form.Item>
              <Button type="primary" htmlType="submit" loading={loading.plus}>执行</Button>
              {result('plus')}
            </Form>
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title="多平台批量注册">
            <Form layout="vertical" initialValues={{ platforms: PLATFORMS }} onFinish={(v) => run('all', () => toolsApi.orchestrateAllPlatforms(v.email, v.password, v.platforms))}>
              <Form.Item name="email" label="邮箱" rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item name="password" label="密码" rules={[{ required: true }]}><Input.Password /></Form.Item>
              <Form.Item name="platforms" label="平台"><Select mode="multiple" options={PLATFORMS.map((p) => ({ value: p, label: p }))} /></Form.Item>
              <Button type="primary" htmlType="submit" loading={loading.all}>执行</Button>
              {result('all')}
            </Form>
          </Card>
        </Col>

        <Col xs={24} lg={12}>
          <Card title="全流程注册">
            <Form layout="vertical" initialValues={{ count: 1, platforms: PLATFORMS }} onFinish={(v) => run('full', () => toolsApi.orchestrateFullFlow(v.count, v.platforms))}>
              <Form.Item name="count" label="数量"><InputNumber min={1} max={100} style={{ width: '100%' }} /></Form.Item>
              <Form.Item name="platforms" label="平台"><Select mode="multiple" options={PLATFORMS.map((p) => ({ value: p, label: p }))} /></Form.Item>
              <Button type="primary" htmlType="submit" loading={loading.full}>执行</Button>
              {result('full')}
            </Form>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
