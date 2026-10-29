import { z } from 'zod'
import { http } from './http'
import {
  actionSchema,
  conversationSchema,
  demoAccountSchema,
  domainsResponseSchema,
  indexedDocumentSchema,
  memoryTurnSchema,
  sessionSchema,
} from './schemas'

const enc = encodeURIComponent

export const api = {
  async login(username: string, password: string) {
    const { data } = await http.post('/auth/login', { username, password })
    return sessionSchema.parse(data)
  },

  async demoAccounts() {
    const { data } = await http.get('/auth/demo-accounts')
    return z.array(demoAccountSchema).parse(data.accounts)
  },

  async demoLogin(account: string) {
    const { data } = await http.post('/auth/demo', { account })
    return sessionSchema.parse(data)
  },

  async domains() {
    const { data } = await http.get('/domains')
    return domainsResponseSchema.parse(data)
  },

  async conversations(domain: string) {
    const { data } = await http.get(`/sessions/${domain}`)
    return z.array(conversationSchema).parse(data.sessions)
  },

  async history(domain: string, threadId: string) {
    const { data } = await http.get(`/sessions/${domain}/${enc(threadId)}`)
    return z.array(memoryTurnSchema).parse(data.turns)
  },

  async deleteConversation(domain: string, threadId: string) {
    await http.delete(`/sessions/${domain}/${enc(threadId)}`)
  },

  async documents(domain: string) {
    const { data } = await http.get(`/documents/${domain}`)
    return z.array(indexedDocumentSchema).parse(data.documents)
  },

  /** `access`: comma-separated groups allowed to retrieve the document; empty for everyone. */
  async uploadDocument(domain: string, file: File, access: string) {
    const body = new FormData()
    body.append('file', file)
    body.append('access', access)
    const { data } = await http.post(`/ingest/${domain}`, body)
    return z.object({ file: z.string(), chunks: z.number(), access: z.array(z.string()) }).parse(data)
  },

  /** Approve or reject a proposal by id only: the server executes what it stored. */
  async decideAction(id: string, decision: 'approve' | 'reject') {
    const { data } = await http.post(`/actions/${enc(id)}/${decision}`)
    return actionSchema.parse(data)
  },

  async deleteDocument(domain: string, filename: string) {
    await http.delete(`/documents/${domain}/${enc(filename)}`)
  },
}
