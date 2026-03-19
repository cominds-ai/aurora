'use client'

import {useEffect, useMemo, useState} from 'react'
import {useRouter} from 'next/navigation'
import {Sidebar, SidebarContent, SidebarFooter, SidebarHeader, SidebarTrigger} from '@/components/ui/sidebar'
import {Button} from '@/components/ui/button'
import {Avatar, AvatarFallback} from '@/components/ui/avatar'
import {Plus} from 'lucide-react'
import {Kbd, KbdGroup} from '@/components/ui/kbd'
import {SessionList} from '@/components/session-list'
import {AuroraSettings} from '@/components/aurora-settings'
import type {AuthUser} from '@/lib/api/types'
import {getAuthSnapshot, subscribeAuthChange} from '@/lib/auth'
import {configApi} from '@/lib/api'

const SANDBOX_WAITING_MESSAGE = '当前暂无沙箱可以分配，请耐心等待'
const API_KEY_MISSING_MESSAGE = '模型 API Key 未配置'
const READY_MESSAGE = 'API Key 与沙箱已就绪'

type CardStatusTone = 'green' | 'yellow' | 'red' | 'neutral'

export function LeftPanel() {
  const router = useRouter()
  const [user, setUser] = useState<AuthUser | null>(null)
  const [cardStatus, setCardStatus] = useState<{tone: CardStatusTone; text: string}>({
    tone: 'neutral',
    text: '',
  })

  useEffect(() => {
    const syncAuth = () => {
      setUser(getAuthSnapshot().user)
    }

    syncAuth()
    return subscribeAuthChange(syncAuth)
  }, [])

  const userInitials = useMemo(() => {
    const source = user?.display_name || user?.username || 'AU'
    return source.slice(0, 2).toUpperCase()
  }, [user])

  useEffect(() => {
    let mounted = true
    let timer: ReturnType<typeof setInterval> | null = null

    const refreshCardStatus = async () => {
      if (!user) {
        if (mounted) {
          setCardStatus({tone: 'neutral', text: ''})
        }
        return
      }

      try {
        const [llmConfig, data] = await Promise.all([
          configApi.getLLMConfig(),
          configApi.getSandboxes(),
        ])
        if (!mounted) return

        if (!llmConfig.api_key_configured) {
          setCardStatus({tone: 'red', text: API_KEY_MISSING_MESSAGE})
          return
        }

        const sandboxes = data.sandboxes || []
        if (sandboxes.some((item) => item.bound_user_id === user.id && item.healthy)) {
          setCardStatus({tone: 'green', text: READY_MESSAGE})
          return
        }
        if (sandboxes.some((item) => item.available && item.healthy)) {
          setCardStatus({tone: 'green', text: READY_MESSAGE})
          return
        }
        setCardStatus({tone: 'yellow', text: SANDBOX_WAITING_MESSAGE})
      } catch (error) {
        if (!mounted) return
        console.error('[LeftPanel] 获取沙箱状态失败:', error)
        setCardStatus({tone: 'yellow', text: SANDBOX_WAITING_MESSAGE})
      }
    }

    refreshCardStatus()
    timer = setInterval(refreshCardStatus, 15000)

    return () => {
      mounted = false
      if (timer) clearInterval(timer)
    }
  }, [user])

  return (
    <Sidebar>
      {/* 顶部的切换按钮 */}
      <SidebarHeader>
        <SidebarTrigger className="cursor-pointer"/>
      </SidebarHeader>
      {/* 中间内容 */}
      <SidebarContent className="flex-1 p-2">
        {/* 新建任务 */}
        <Button
          variant="outline"
          className="cursor-pointer mb-3"
          onClick={() => router.push('/')}
        >
          <Plus/>
          新建任务
          <KbdGroup>
            <Kbd>⌘</Kbd>
            <Kbd>K</Kbd>
          </KbdGroup>
        </Button>
        {/* 会话列表 */}
        <SessionList/>
      </SidebarContent>
      <SidebarFooter className="border-t border-stone-200/80 p-3">
        <div
          className={`rounded-2xl p-3 shadow-sm ${
            cardStatus.tone === 'green'
              ? 'border border-emerald-200 bg-emerald-50/70'
              : cardStatus.tone === 'yellow'
                ? 'border border-amber-200 bg-amber-50/80'
                : cardStatus.tone === 'red'
                  ? 'border border-rose-200 bg-rose-50/80'
                  : 'border border-stone-200/80 bg-white'
          }`}
        >
          <div className="flex items-center gap-3">
            <Avatar className="size-10 shrink-0">
              <AvatarFallback
                className={`text-sm text-white ${
                  cardStatus.tone === 'green'
                    ? 'bg-emerald-700'
                    : cardStatus.tone === 'yellow'
                      ? 'bg-amber-700'
                      : cardStatus.tone === 'red'
                        ? 'bg-rose-700'
                        : 'bg-stone-900'
                }`}
              >
                {userInitials}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-stone-900">
                {user?.display_name || '当前用户'}
              </div>
              <div className="truncate text-xs text-stone-500">
                {user?.username || '未命名账号'}
              </div>
            </div>
            <AuroraSettings
              triggerSize="icon-sm"
              triggerClassName="ml-auto self-start rounded-full border-stone-200 bg-stone-50 text-stone-700 shadow-none hover:bg-stone-100"
            />
          </div>
          {cardStatus.text && (
            <div
              className={`mt-3 inline-flex max-w-full items-center gap-2 rounded-full px-3 py-1.5 text-[11px] font-medium leading-4 ${
                cardStatus.tone === 'green'
                  ? 'bg-emerald-100 text-emerald-800 ring-1 ring-emerald-200'
                  : cardStatus.tone === 'yellow'
                    ? 'bg-amber-100 text-amber-800 ring-1 ring-amber-200'
                    : cardStatus.tone === 'red'
                      ? 'bg-rose-100 text-rose-800 ring-1 ring-rose-200'
                      : 'bg-stone-100 text-stone-700 ring-1 ring-stone-200'
              }`}
            >
              <span
                className={`size-1.5 shrink-0 rounded-full ${
                  cardStatus.tone === 'green'
                    ? 'bg-emerald-500'
                    : cardStatus.tone === 'yellow'
                      ? 'bg-amber-500'
                      : cardStatus.tone === 'red'
                        ? 'bg-rose-500'
                        : 'bg-stone-400'
                }`}
              />
              <span className="truncate">{cardStatus.text}</span>
            </div>
          )}
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}
