import { useMutation } from '@tanstack/react-query'
import { Loader2, LogIn, ShieldCheck, UserRound } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router'
import { api } from '@/api/endpoints'
import type { DemoAccount } from '@/api/schemas'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useSession } from '@/hooks/use-auth'
import { useDemoAccounts } from '@/hooks/queries'
import { useAuthStore } from '@/stores/auth-store'

const DOMAIN_LABELS: Record<string, string> = { hr: 'HR', it: 'IT', cloudops: 'CloudOps' }

/** What each demo account can do that the others cannot, shown under its button. */
function describe(account: DemoAccount): string {
  const domains = account.domains.map((d) => DOMAIN_LABELS[d] ?? d).join(', ')
  if (account.role === 'admin') return `${domains} · manages documents`
  if (account.groups.length) return `${domains} · sees confidential HR documents`
  return `${domains} · public documents only`
}

export function LoginPage() {
  const token = useAuthStore((s) => s.token)
  const location = useLocation()
  const { signIn } = useSession()
  const from = (location.state as { from?: string } | null)?.from ?? '/'
  const demo = useDemoAccounts()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')

  useEffect(() => {
    document.title = 'Sign in · Enterprise Copilot'
  }, [])

  const login = useMutation({
    mutationFn: (request: { account: string } | { username: string; password: string }) =>
      'account' in request ? api.demoLogin(request.account) : api.login(request.username, request.password),
    onSuccess: (session) => signIn(session.access_token, session.user, from),
  })

  if (token) return <Navigate to={from} replace />

  const submit = (e: FormEvent) => {
    e.preventDefault()
    login.mutate({ username, password })
  }

  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <div className="w-full max-w-md space-y-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <div className="flex size-10 items-center justify-center rounded-xl bg-primary text-sm font-bold text-primary-foreground">EC</div>
          <h1 className="text-xl font-semibold tracking-tight">Sign in to Enterprise Copilot</h1>
          <p className="text-sm text-muted-foreground">Each account sees only the assistants and documents it is allowed to.</p>
        </div>

        {demo.data?.length ? (
          <section aria-labelledby="demo-title" className="space-y-2">
            <h2 id="demo-title" className="text-sm font-medium">Try a demo account</h2>
            <ul className="grid gap-2">
              {demo.data.map((account) => (
                <li key={account.account}>
                  <button
                    type="button"
                    onClick={() => login.mutate({ account: account.account })}
                    disabled={login.isPending}
                    className="flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors hover:bg-muted/50 disabled:opacity-50"
                  >
                    {account.role === 'admin' ? (
                      <ShieldCheck className="size-5 shrink-0 text-muted-foreground" aria-hidden />
                    ) : (
                      <UserRound className="size-5 shrink-0 text-muted-foreground" aria-hidden />
                    )}
                    <span className="min-w-0">
                      <span className="block text-sm font-medium">{account.display_name}</span>
                      <span className="block text-xs text-muted-foreground">{describe(account)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <form onSubmit={submit} className="space-y-3 rounded-xl border p-4" aria-label="Sign in with a password">
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">Username</span>
            <Input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </label>
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">Password</span>
            <Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </label>
          <Button type="submit" className="w-full" disabled={login.isPending}>
            {login.isPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <LogIn data-icon="inline-start" />}
            Sign in
          </Button>
        </form>

        {login.error ? (
          <p role="alert" className="text-center text-sm text-destructive">
            {login.error.message}
          </p>
        ) : null}
      </div>
    </main>
  )
}
