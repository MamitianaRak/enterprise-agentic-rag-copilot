import { http, HttpResponse } from 'msw'

export const HR_DOMAIN = {
  name: 'hr',
  label: 'HR Policy',
  title: 'HR Policy & Employee Support',
  tagline: 'Answers from the company HR knowledge base first.',
  placeholder: 'Ask an HR policy question…',
  documents_label: 'HR documents',
  web_warning: 'External information: validate with HR.',
  accent: '#1f9d63',
  examples: ['How many annual leave days do employees receive?'],
}

export const CHAT_RESULT = {
  domain: 'hr',
  thread_id: 'thread-1',
  memory_turns: 1,
  answer: 'Employees receive **20 days** of annual leave.',
  source_used: 'private_kb',
  trace: ['Memory → new conversation', 'Router → KB', 'Support check → FULLY_SUPPORTED'],
  citations: [
    { title: 'company_hr_handbook.md', url: '', type: 'private_kb', page: null, excerpt: 'Employees receive 20 annual leave days.' },
  ],
  rewritten_query: 'annual leave days',
  support_status: 'fully_supported',
  usefulness: 'useful',
}

export const ADMIN_USER = {
  username: 'admin',
  display_name: 'Demo admin',
  role: 'admin' as const,
  domains: ['hr', 'it', 'cloudops'],
  groups: ['hr-managers'],
}

export const EMPLOYEE_USER = {
  username: 'alex',
  display_name: 'Alex Martin (employee)',
  role: 'employee' as const,
  domains: ['hr', 'it'],
  groups: [],
}

export function sse(events: Array<[string, unknown]>) {
  return events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('')
}

export const handlers = [
  http.get('*/api/auth/demo-accounts', () =>
    HttpResponse.json({
      accounts: [
        { account: 'employee', ...EMPLOYEE_USER },
        { account: 'admin', ...ADMIN_USER },
      ],
    }),
  ),
  http.post('*/api/auth/demo', () => HttpResponse.json({ access_token: 'employee-token', user: EMPLOYEE_USER })),
  http.get('*/api/domains', () => HttpResponse.json({ default: 'hr', domains: [HR_DOMAIN] })),
  http.get('*/api/sessions/hr', () =>
    HttpResponse.json({
      domain: 'hr',
      sessions: [
        { thread_id: 'old-1', title: 'Remote work policy?', turns: 2, created_at: '2026-10-17T10:00:00Z', updated_at: '2026-10-17T10:05:00Z' },
      ],
    }),
  ),
  http.get('*/api/sessions/hr/:threadId', () => HttpResponse.json({ turns: [] })),
  http.post('*/api/chat/hr/stream', () =>
    new HttpResponse(
      sse([
        ['start', { thread_id: 'thread-1' }],
        ...CHAT_RESULT.trace.map((line) => ['step', { line }] as [string, unknown]),
        ['result', CHAT_RESULT],
      ]),
      { headers: { 'Content-Type': 'text/event-stream' } },
    ),
  ),
]
