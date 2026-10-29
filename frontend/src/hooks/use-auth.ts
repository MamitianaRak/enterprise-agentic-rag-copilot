import { useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { useNavigate } from 'react-router'
import type { SessionUser } from '@/api/schemas'
import { useAuthStore } from '@/stores/auth-store'

/**
 * Sign in and out. The query cache is cleared on both, so one account never sees the
 * conversations or documents cached for the previous one.
 */
export function useSession() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)

  const signIn = useCallback(
    (token: string, sessionUser: SessionUser, to = '/') => {
      queryClient.clear()
      useAuthStore.getState().signIn(token, sessionUser)
      navigate(to, { replace: true })
    },
    [queryClient, navigate],
  )

  const signOut = useCallback(() => {
    queryClient.clear()
    useAuthStore.getState().signOut()
    navigate('/login', { replace: true })
  }, [queryClient, navigate])

  return { user, isAdmin: user?.role === 'admin', signIn, signOut }
}
