import { ListTree, LogOut, Menu } from 'lucide-react'
import { useNavigate } from 'react-router'
import type { DomainConfig } from '@/api/schemas'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useSession } from '@/hooks/use-auth'
import { useAppStore } from '@/stores/app-store'
import { ThemeToggle } from './ThemeToggle'

export function Header({ domains, current }: { domains: DomainConfig[]; current: string }) {
  const navigate = useNavigate()
  const setSidebarOpen = useAppStore((s) => s.setSidebarOpen)
  const setInspectorOpen = useAppStore((s) => s.setInspectorOpen)
  const { user, signOut } = useSession()

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b px-3 sm:px-4">
      <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setSidebarOpen(true)} aria-label="Open conversations">
        <Menu />
      </Button>
      <div className="flex items-center gap-2">
        <div className="flex size-8 items-center justify-center rounded-lg bg-(--domain) text-xs font-bold text-white">EC</div>
        <span className="hidden font-semibold tracking-tight sm:inline">Enterprise Copilot</span>
      </div>

      <Tabs value={current} onValueChange={(value) => navigate(`/${value}`)} className="ml-2 min-w-0">
        <TabsList aria-label="Knowledge domain">
          {domains.map((d) => (
            <TabsTrigger key={d.name} value={d.name}>
              {d.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <div className="ml-auto flex items-center gap-1">
        <Button variant="ghost" size="icon" className="xl:hidden" onClick={() => setInspectorOpen(true)} aria-label="Open agent trace">
          <ListTree />
        </Button>
        <ThemeToggle />
        {user ? (
          <div className="ml-1 flex items-center gap-1 border-l pl-2">
            <span className="hidden max-w-48 truncate text-sm text-muted-foreground lg:inline" title={user.display_name}>
              {user.display_name}
            </span>
            <Button variant="ghost" size="icon" onClick={signOut} aria-label="Sign out" title="Sign out">
              <LogOut />
            </Button>
          </div>
        ) : null}
      </div>
    </header>
  )
}
