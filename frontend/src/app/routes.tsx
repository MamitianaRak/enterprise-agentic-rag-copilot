import { Navigate, type RouteObject } from 'react-router'
import { ChatPage } from '@/routes/ChatPage'
import { LoginPage } from '@/routes/LoginPage'
import { RequireAuth } from '@/routes/RequireAuth'
import { RootRedirect } from '@/routes/RootRedirect'

export const routes: RouteObject[] = [
  { path: '/login', element: <LoginPage /> },
  {
    element: <RequireAuth />,
    children: [
      { path: '/', element: <RootRedirect /> },
      { path: '/:domain', element: <ChatPage /> },
      { path: '/:domain/c/:threadId', element: <ChatPage /> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]
