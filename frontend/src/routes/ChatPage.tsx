import { useCallback, useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router'
import { ChatView } from '@/components/chat/ChatView'
import { Inspector } from '@/components/chat/Inspector'
import { AppShell } from '@/components/layout/AppShell'
import { Header } from '@/components/layout/Header'
import { Sidebar } from '@/components/layout/Sidebar'
import { useChat } from '@/hooks/use-chat'
import { useCurrentDomain } from '@/hooks/use-domain'

/** /:domain (new chat) and /:domain/c/:threadId (existing conversation). */
export function ChatPage() {
  const navigate = useNavigate()
  const { domains, domain, domainName, threadId, loaded } = useCurrentDomain()

  const onThreadCreated = useCallback(
    (id: string) => navigate(`/${domainName}/c/${id}`, { replace: true }),
    [navigate, domainName],
  )
  const chat = useChat(domainName, threadId, onThreadCreated)

  // The inspector follows the newest answer, unless the user picked another one since the
  // last message arrived in this conversation.
  const [pick, setPick] = useState<{ id: string; threadId?: string; count: number }>()
  const pickIsCurrent = pick?.threadId === threadId && pick?.count === chat.messages.length
  const selected =
    (pickIsCurrent ? chat.messages.find((m) => m.id === pick.id) : undefined) ??
    chat.messages.findLast((m) => m.role === 'assistant')
  const select = (id: string) => setPick({ id, threadId, count: chat.messages.length })

  useEffect(() => {
    if (domain) document.title = `${domain.label} · Enterprise Copilot`
  }, [domain])

  if (loaded && !domain) return <Navigate to="/" replace />
  if (!domain) return null

  return (
    <AppShell
      accent={domain.accent}
      header={<Header domains={domains} current={domain.name} />}
      sidebar={(close) => <Sidebar domain={domain} activeThread={threadId} onNavigate={close} />}
      inspector={<Inspector message={selected} />}
    >
      <ChatView
        domain={domain}
        messages={chat.messages}
        loading={chat.loading}
        busy={chat.busy}
        selectedId={selected?.id}
        onSelect={select}
        onSend={chat.send}
      />
    </AppShell>
  )
}
