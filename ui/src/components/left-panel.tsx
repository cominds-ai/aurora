'use client'

import {useEffect, useMemo, useState} from 'react'
import {useRouter} from 'next/navigation'
import {Sidebar, SidebarContent, SidebarFooter, SidebarHeader, SidebarTrigger} from '@/components/ui/sidebar'
import {Button} from '@/components/ui/button'
import {Avatar, AvatarFallback} from '@/components/ui/avatar'
import {LogOut, Plus} from 'lucide-react'
import {Kbd, KbdGroup} from '@/components/ui/kbd'
import {SessionList} from '@/components/session-list'
import type {AuthUser} from '@/lib/api/types'
import {clearAuthSession, getAuthSnapshot, subscribeAuthChange} from '@/lib/auth'
import {toast} from 'sonner'

export function LeftPanel() {
  const router = useRouter()
  const [user, setUser] = useState<AuthUser | null>(null)

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

  const handleLogout = () => {
    clearAuthSession()
    toast.success('已退出登录')
    router.replace('/')
  }

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
        <div className="rounded-2xl bg-stone-100/80 p-3">
          <div className="flex items-center gap-3">
            <Avatar className="size-10">
              <AvatarFallback className="bg-stone-900 text-sm text-white">
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
          </div>
          <Button
            variant="outline"
            className="mt-3 w-full cursor-pointer justify-start rounded-xl border-stone-200 bg-white"
            onClick={handleLogout}
          >
            <LogOut/>
            退出登录
          </Button>
        </div>
      </SidebarFooter>
    </Sidebar>
  )
}
