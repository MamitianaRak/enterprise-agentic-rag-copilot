import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { createQueryClient } from '@/app/query-client'
import { routes } from '@/app/routes'
import { TooltipProvider } from '@/components/ui/tooltip'
import { CHAT_RESULT, sse } from '@/test/handlers'
import { server } from '@/test/setup'

const PROPOSAL = {
  id: 'a'.repeat(32),
  kind: 'hr_case',
  label: 'HR case',
  status: 'proposed',
  title: 'My manager keeps harassing me',
  priority: 'confidential',
  reason: 'Sensitive topic: an HR partner should follow up.',
  reference: '',
  created_at: '2026-10-29T10:00:00Z',
}

function renderChat() {
  const router = createMemoryRouter(routes, { initialEntries: ['/hr'] })
  render(
    <QueryClientProvider client={createQueryClient()}>
      <TooltipProvider>
        <RouterProvider router={router} />
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

function answerWithProposal() {
  server.use(
    http.post('*/api/chat/hr/stream', () =>
      new HttpResponse(sse([['result', { ...CHAT_RESULT, proposed_action: PROPOSAL }]]), {
        headers: { 'Content-Type': 'text/event-stream' },
      }),
    ),
  )
}

describe('Proposed actions', () => {
  it('creates the ticket only after the user approves it', async () => {
    answerWithProposal()
    let approvals = 0
    server.use(
      http.post('*/api/actions/:id/approve', () => {
        approvals += 1
        return HttpResponse.json({ ...PROPOSAL, status: 'executed', reference: 'HR-1001' })
      }),
    )
    const user = userEvent.setup()
    renderChat()
    await user.type(await screen.findByRole('textbox', { name: 'Your question' }), 'My manager keeps harassing me{Enter}')

    const card = await screen.findByRole('region', { name: 'Proposed HR case' })
    expect(card).toHaveTextContent('Sensitive topic')
    expect(approvals).toBe(0)

    await user.click(screen.getByRole('button', { name: 'Approve' }))
    expect(await screen.findByText(/HR case HR-1001 created/, { selector: 'p' })).toBeInTheDocument()
    expect(approvals).toBe(1)
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
  })

  it('dismisses a proposal without creating anything', async () => {
    answerWithProposal()
    server.use(http.post('*/api/actions/:id/reject', () => HttpResponse.json({ ...PROPOSAL, status: 'rejected' })))
    const user = userEvent.setup()
    renderChat()
    await user.type(await screen.findByRole('textbox', { name: 'Your question' }), 'My manager keeps harassing me{Enter}')
    await user.click(await screen.findByRole('button', { name: 'Dismiss' }))
    expect(await screen.findByText('Dismissed, nothing was created')).toBeInTheDocument()
  })
})
