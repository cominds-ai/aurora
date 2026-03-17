import React from 'react'
import type {Metadata} from 'next'
import {Toaster} from '@/components/ui/sonner'
import './globals.css'
import {AppShell} from '@/components/app-shell'

export const metadata: Metadata = {
  title: 'Aurora',
  description: 'Aurora 是一个可部署在本地与 DSW 上的多用户智能体平台。',
  icons: {
    icon: '/icon.png',
  },
}

export default function RootLayout(
  {
    children,
  }: Readonly<{
    children: React.ReactNode;
  }>,
) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
    <body className="h-screen overflow-hidden">
    <AppShell>{children}</AppShell>
    <Toaster position="top-center" richColors/>
    </body>
    </html>
  )
}
