'use client'

import {FormEvent, useEffect, useRef, useState} from 'react'
import {useRouter} from 'next/navigation'
import {ChatHeader} from '@/components/chat-header'
import {ChatInput, type ChatInputRef} from '@/components/chat-input'
import {SandboxConnectionPrompt} from '@/components/sandbox-connection-prompt'
import {SuggestedQuestions} from '@/components/suggested-questions'
import {Button} from '@/components/ui/button'
import {Input} from '@/components/ui/input'
import {authApi} from '@/lib/api/auth'
import {sessionApi} from '@/lib/api/session'
import type {FileInfo} from '@/lib/api/types'
import {clearAuthSession, getAuthSnapshot, setAuthSession, subscribeAuthChange} from '@/lib/auth'
import {toast} from 'sonner'

export default function Page() {
  const router = useRouter()
  const chatInputRef = useRef<ChatInputRef>(null)
  const [checkingAuth, setCheckingAuth] = useState(true)
  const [authenticated, setAuthenticated] = useState(false)
  const [sending, setSending] = useState(false)
  const [loggingIn, setLoggingIn] = useState(false)
  const [username, setUsername] = useState('')

  useEffect(() => {
    let mounted = true

    const syncAuth = () => {
      if (!mounted) return
      setAuthenticated(getAuthSnapshot().authenticated)
    }

    const unsubscribe = subscribeAuthChange(syncAuth)

    const bootstrap = async () => {
      const snapshot = getAuthSnapshot()
      syncAuth()

      if (!snapshot.accessToken) {
        if (mounted) {
          setCheckingAuth(false)
        }
        return
      }

      try {
        const user = await authApi.me()
        if (!mounted) return
        setAuthSession(snapshot.accessToken, user)
        setAuthenticated(true)
      } catch {
        if (!mounted) return
        clearAuthSession()
        setAuthenticated(false)
      } finally {
        if (mounted) {
          setCheckingAuth(false)
        }
      }
    }

    bootstrap()

    return () => {
      mounted = false
      unsubscribe()
    }
  }, [])

  const handleQuestionClick = (question: string) => {
    chatInputRef.current?.setInputText(question)
  }

  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!username.trim()) {
      toast.error('请输入账号')
      return
    }

    setLoggingIn(true)
    try {
      const result = await authApi.login({
        username: username.trim(),
        password: '123456',
      })
      setAuthSession(result.token.access_token, result.user)
      setAuthenticated(true)
      toast.success(`已登录为 ${result.user.display_name}`)
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '登录失败'
      toast.error(errorMessage)
    } finally {
      setLoggingIn(false)
    }
  }

  const handleSend = async (message: string, files: FileInfo[]) => {
    if (sending) return

    setSending(true)

    try {
      // 1. 创建新会话
      const session = await sessionApi.createSession()
      const sessionId = session.session_id

      // 2. 将消息数据编码到 URL，在详情页发送
      const attachments = files.map((file) => file.id)
      const payload = JSON.stringify({ message, attachments })
      // 使用 Base64 编码避免 URL 特殊字符问题
      const encoded = btoa(encodeURIComponent(payload))
      
      // 3. 跳转到详情页，携带编码后的初始消息
      router.push(`/sessions/${sessionId}?init=${encoded}`)
      
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '创建会话失败'
      toast.error(errorMessage)
      setSending(false)
      throw error
    }
  }

  if (checkingAuth) {
    return <div className="h-full flex items-center justify-center text-gray-500">加载中...</div>
  }

  if (!authenticated) {
    return (
      <div className="min-h-screen bg-[radial-gradient(circle_at_top,#fff7d6,transparent_45%),linear-gradient(135deg,#fffdf5,#f2f4ea)] flex items-center justify-center px-4">
        <div className="w-full max-w-md rounded-[32px] border border-amber-100 bg-white/90 p-8 shadow-[0_24px_80px_rgba(145,124,42,0.12)]">
          <div className="mb-8">
            <div className="text-sm uppercase tracking-[0.3em] text-amber-500">Aurora</div>
            <h1 className="mt-3 text-3xl font-semibold text-stone-900">地球人入口</h1>
            <p className="mt-3 text-sm leading-6 text-stone-500">
              输入账号即可登录。首次登录会自动注册，默认密码固定为 <code>123456</code>。
            </p>
          </div>
          <form className="space-y-4" onSubmit={handleLogin}>
            <Input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入账号名"
              className="h-12 rounded-2xl border-stone-200"
            />
            <Button type="submit" className="h-12 w-full rounded-2xl bg-stone-900 hover:bg-stone-800" disabled={loggingIn}>
              {loggingIn ? '登录中...' : '登录 / 自动注册'}
            </Button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">
      {/* 顶部header */}
      <ChatHeader/>
      {/* 中间对话框 - 垂直居中，视觉上移一个导航栏高度 */}
      <div className="flex-1 flex items-center justify-center px-4 py-6 sm:py-8 -mt-12 sm:-mt-16">
        <div className="w-full max-w-full sm:max-w-[768px] sm:min-w-[390px] mx-auto">
          {/* 对话提示内容 */}
          <div className="text-[24px] sm:text-[32px] font-bold mb-4 sm:mb-6 text-center sm:text-left">
            <div className="text-gray-700">您好, 地球人</div>
            <div className="text-gray-500">我能为您做什么?</div>
          </div>
          <SandboxConnectionPrompt />
          {/* 对话框 */}
          <ChatInput
            ref={chatInputRef}
            className="mb-4 sm:mb-6"
            onSend={handleSend}
            disabled={sending}
          />
          {/* 推荐对话内容 */}
          <SuggestedQuestions onQuestionClick={handleQuestionClick}/>
        </div>
      </div>
    </div>
  )
}
