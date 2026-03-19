'use client'

import {useEffect, useState} from 'react'
import {AlertTriangle} from 'lucide-react'
import {configApi} from '@/lib/api'
import {getAuthSnapshot} from '@/lib/auth'

const SANDBOX_PROMPT_MESSAGE = '当前系统还未配置可用的沙箱池'

export function SandboxConnectionPrompt() {
  const [loading, setLoading] = useState(true)
  const [configured, setConfigured] = useState(false)
  const [message, setMessage] = useState(SANDBOX_PROMPT_MESSAGE)
  const isAdmin = getAuthSnapshot().user?.username === 'fh'

  useEffect(() => {
    let mounted = true

    configApi
      .getSandboxPreferenceStatus()
      .then((status) => {
        if (!mounted) return
        setConfigured(status.configured)
        setMessage(status.message || SANDBOX_PROMPT_MESSAGE)
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

  if (loading || configured) {
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
            {message}
            {isAdmin ? '。请在设置面板的“沙箱池”中维护实例 IP。' : '。请联系管理员维护沙箱池。'}
          </div>
        </div>
      </div>
    </div>
  )
}
