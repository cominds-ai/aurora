'use client'

import type { CSSProperties } from 'react'
import { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { SidebarProvider } from '@/components/ui/sidebar'
import { SessionsProvider } from '@/providers/sessions-provider'
import { LeftPanel } from '@/components/left-panel'
import { getAuthSnapshot, subscribeAuthChange } from '@/lib/auth'

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const [authenticated, setAuthenticated] = useState(false)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const syncAuth = () => {
      setAuthenticated(getAuthSnapshot().authenticated)
      setReady(true)
    }

    syncAuth()
    return subscribeAuthChange(syncAuth)
  }, [])

  useEffect(() => {
    if (!ready) return

    if (!authenticated && pathname !== '/') {
      router.replace('/')
    }
  }, [authenticated, pathname, ready, router])

  if (!ready) {
    return <div className="h-screen flex items-center justify-center text-gray-500">加载中...</div>
  }

  const shellStyle = {
    '--sidebar-width': '300px',
    '--sidebar-width-icon': '300px',
  } as CSSProperties

  if (!authenticated) {
    return (
      <SidebarProvider style={shellStyle}>
        <div className="flex-1 bg-[#f8f8f7] h-screen overflow-hidden">{children}</div>
      </SidebarProvider>
    )
  }

  return (
    <SessionsProvider>
      <SidebarProvider style={shellStyle}>
        <LeftPanel />
        <div className="flex-1 bg-[#f8f8f7] h-screen overflow-hidden">
          {children}
        </div>
      </SidebarProvider>
    </SessionsProvider>
  )
}
