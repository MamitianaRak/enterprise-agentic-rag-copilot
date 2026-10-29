import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { createQueryClient } from '@/app/query-client'
import { routes } from '@/app/routes'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useAuthStore } from '@/stores/auth-store'
import { EMPLOYEE_USER, HR_DOMAIN } from '@/test/handlers'
import { server } from '@/test/setup'

const CLOUDOPS = { ...HR_DOMAIN, name: 'cloudops', label: 'CloudOps', title: 'CloudOps Incident Response' }

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(
    <QueryClientProvider client={createQueryClient()}>
      <TooltipProvider>
        <RouterProvider router={router} />
      </TooltipProvider>
    </QueryClientProvider>,
  )
  return router
}

describe('Authentication', () => {
  it('sends a visitor without a session to the login page', async () => {
    useAuthStore.getState().signOut()
    const router = renderAt('/hr')
    expect(await screen.findByRole('heading', { name: 'Sign in to Enterprise Copilot' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
  })

  it('signs in with a demo account and lands on an allowed assistant', async () => {
    useAuthStore.getState().signOut()
    const user = userEvent.setup()
    const router = renderAt('/login')
    await user.click(await screen.findByRole('button', { name: /Alex Martin/ }))
    expect(await screen.findByRole('heading', { name: 'HR Policy & Employee Support' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/hr')
    expect(useAuthStore.getState().user?.username).toBe('alex')
  })

  it('shows only the domains of the account and blocks the others', async () => {
    useAuthStore.getState().signIn('employee-token', EMPLOYEE_USER)
    server.use(http.get('*/api/domains', () => HttpResponse.json({ default: 'hr', domains: [HR_DOMAIN, CLOUDOPS] })))
    const router = renderAt('/cloudops')
    expect(await screen.findByRole('heading', { name: 'HR Policy & Employee Support' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/hr')
    expect(screen.queryByRole('tab', { name: 'CloudOps' })).not.toBeInTheDocument()
  })

  it('signs out when the API rejects the session', async () => {
    server.use(http.get('*/api/sessions/hr', () => HttpResponse.json({ detail: 'Your session has expired.' }, { status: 401 })))
    const router = renderAt('/hr')
    expect(await screen.findByRole('heading', { name: 'Sign in to Enterprise Copilot' })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
    expect(useAuthStore.getState().token).toBeNull()
  })

  it('shows a wrong password error', async () => {
    useAuthStore.getState().signOut()
    server.use(http.post('*/api/auth/login', () => HttpResponse.json({ detail: 'Wrong username or password.' }, { status: 401 })))
    const user = userEvent.setup()
    renderAt('/login')
    await user.type(await screen.findByLabelText('Username'), 'jdoe')
    await user.type(screen.getByLabelText('Password'), 'nope')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Wrong username or password.')
  })

  it('hides upload and delete from a non-admin', async () => {
    useAuthStore.getState().signIn('employee-token', EMPLOYEE_USER)
    server.use(
      http.get('*/api/documents/hr', () =>
        HttpResponse.json({
          documents: [{ filename: 'company_hr_handbook.md', chunks: 3, indexed_at: '2026-10-29T10:00:00Z', access: ['all'] }],
        }),
      ),
    )
    const user = userEvent.setup()
    renderAt('/hr')
    await user.click(await screen.findByRole('button', { name: /HR documents/ }))
    expect(await screen.findByText('company_hr_handbook.md')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Index document/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Remove company_hr_handbook.md/ })).not.toBeInTheDocument()
  })
})
