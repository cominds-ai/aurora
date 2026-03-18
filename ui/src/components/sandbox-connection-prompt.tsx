'use client'

import {useCallback, useEffect, useState} from 'react'
import { AlertTriangle, Loader2 } from 'lucide-react'
import {toast} from 'sonner'
import {Button} from '@/components/ui/button'
import {Input} from '@/components/ui/input'
import {configApi} from '@/lib/api'

const SANDBOX_PROMPT_MESSAGE = '您还未连接沙箱地址，请联系风后（田萧波）提供'

export function SandboxConnectionPrompt() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [sandboxHost, setSandboxHost] = useState('')
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let mounted = true

    configApi
      .getSandboxPreferenceStatus()
      .then((status) => {
        if (!mounted) return
        const host = status.preferred_sandbox_host?.trim() ?? ''
        setSandboxHost(host)
        setConnected(status.connected)
        if (status.needs_reconfigure && status.message) {
          toast.error(status.message)
        }
      })
      .catch((error) => {
        if (!mounted) return
        console.error('[SandboxPrompt] 获取沙箱配置失败:', error)
      })
      .finally(() => {
        if (mounted) {
          setLoading(false)
        }
      })

    return () => {
      mounted = false
    }
  }, [])

  const handleSave = useCallback(async () => {
    const trimmedHost = sandboxHost.trim()
    if (!trimmedHost) {
      toast.error(SANDBOX_PROMPT_MESSAGE)
      return
    }

    setSaving(true)
    try {
      const updated = await configApi.updateSandboxPreference({
        preferred_sandbox_host: trimmedHost,
      })
      const host = updated.preferred_sandbox_host?.trim() ?? trimmedHost
      setSandboxHost(host)
      setConnected(Boolean(host))
      toast.success('沙箱地址已保存')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存沙箱地址失败')
    } finally {
      setSaving(false)
    }
  }, [sandboxHost])

  if (loading || connected) {
    return null
  }

  return (
    <div className="mb-4 rounded-3xl border border-amber-200 bg-[linear-gradient(135deg,#fffaf0,#fff4d8)] p-4 shadow-[0_18px_50px_rgba(180,132,33,0.10)]">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-2xl bg-amber-100 text-amber-700">
          <AlertTriangle size={18} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-amber-900">{SANDBOX_PROMPT_MESSAGE}</div>
          <div className="mt-1 text-sm leading-6 text-amber-800/80">
            拿到地址后，直接在这里填写并保存即可。Aurora 会按固定端口连接该沙箱。
          </div>
          <div className="mt-3 flex flex-col gap-2 sm:flex-row">
            <Input
              value={sandboxHost}
              onChange={(e) => setSandboxHost(e.target.value)}
              placeholder="请输入沙箱 IP 或域名"
              className="h-11 rounded-2xl border-amber-200 bg-white/80"
              disabled={saving}
            />
            <Button
              type="button"
              className="h-11 rounded-2xl bg-amber-900 text-white hover:bg-amber-800"
              disabled={saving}
              onClick={handleSave}
            >
              {saving && <Loader2 className="animate-spin" />}
              保存地址
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
