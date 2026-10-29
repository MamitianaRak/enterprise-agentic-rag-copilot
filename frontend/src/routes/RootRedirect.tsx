import { Loader2, ServerCrash } from 'lucide-react'
import { Navigate } from 'react-router'
import { Button } from '@/components/ui/button'
import { useDomains } from '@/hooks/queries'
import { useAuthStore } from '@/stores/auth-store'

/** "/" sends the user to the default domain, or to the first one their account may use. */
export function RootRedirect() {
  const { data, error, refetch, isFetching } = useDomains()
  const allowed = useAuthStore((s) => s.user?.domains ?? [])

  if (data) {
    const usable = data.domains.filter((d) => allowed.includes(d.name)).map((d) => d.name)
    const target = usable.includes(data.default) ? data.default : usable[0]
    if (target) return <Navigate to={`/${target}`} replace />
    return (
      <div className="flex h-dvh items-center justify-center p-6 text-center text-sm text-muted-foreground">
        Your account has no access to any assistant yet. Ask an administrator.
      </div>
    )
  }

  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-4 p-6 text-center">
      {error ? (
        <>
          <ServerCrash className="size-10 text-muted-foreground" aria-hidden />
          <div>
            <h1 className="text-lg font-semibold">Cannot reach the backend</h1>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">{error.message}</p>
          </div>
          <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
            Try again
          </Button>
        </>
      ) : (
        <Loader2 className="size-6 animate-spin text-muted-foreground" aria-label="Loading" />
      )}
    </div>
  )
}
