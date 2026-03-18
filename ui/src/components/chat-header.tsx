'use client'

import Link from 'next/link'
import {Sparkles} from 'lucide-react'
import {SidebarTrigger, useSidebar} from '@/components/ui/sidebar'

export function ChatHeader() {
  const {open, isMobile} = useSidebar()

  return (
    <header className="flex items-center w-full py-2 px-4 z-50">
      {/* 左侧操作&logo */}
      <div className="flex items-center gap-2">
        {/* 面板操作按钮: 关闭面板&移动端下会显示 */}
        {(!open || isMobile) && <SidebarTrigger className="cursor-pointer"/>}
        <Link href="/" className="flex items-center gap-2 rounded-md bg-white px-3 py-2 text-stone-800 shadow-sm">
          <Sparkles size={16}/>
          <span className="text-sm font-semibold tracking-[0.2em] uppercase">Aurora</span>
        </Link>
      </div>
    </header>
  )
}
