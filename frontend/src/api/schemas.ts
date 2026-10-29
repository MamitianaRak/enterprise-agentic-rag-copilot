// Runtime schemas for the FastAPI responses (app/api/*.py). Types are inferred from them,
// so the frontend can never silently drift from what the backend actually sends.
import { z } from 'zod'

export const domainConfigSchema = z.object({
  name: z.string(),
  label: z.string(),
  title: z.string(),
  tagline: z.string(),
  placeholder: z.string(),
  documents_label: z.string(),
  web_warning: z.string(),
  accent: z.string(),
  examples: z.array(z.string()),
})

export const domainsResponseSchema = z.object({
  default: z.string(),
  domains: z.array(domainConfigSchema),
})

export const sourceUsedSchema = z.enum(['private_kb', 'web_search', 'direct', 'insufficient_evidence'])

export const citationSchema = z.object({
  title: z.string(),
  url: z.string().default(''),
  type: z.enum(['private_kb', 'web']),
  page: z.number().nullish(),
  excerpt: z.string().optional(),
})

/** Triage of graded-retrieval domains: incident severity (CloudOps) or ticket priority (IT); null for HR. */
export const triageSchema = z.object({
  severity: z.enum(['SEV1', 'SEV2', 'SEV3', 'SEV4', 'P1', 'P2', 'P3', 'P4', 'none']),
  service: z.string(),
  category: z.string(),
})

export const chatResponseSchema = z.object({
  domain: z.string(),
  thread_id: z.string(),
  memory_turns: z.number(),
  answer: z.string(),
  source_used: sourceUsedSchema,
  trace: z.array(z.string()),
  citations: z.array(citationSchema),
  rewritten_query: z.string(),
  support_status: z.enum(['fully_supported', 'partially_supported', 'no_support', '']),
  usefulness: z.string(),
  triage: triageSchema.nullish(),
})

export const memoryTurnSchema = z.object({
  question: z.string(),
  answer: z.string(),
  source_used: sourceUsedSchema,
  citations: z.array(citationSchema).default([]),
})

export const conversationSchema = z.object({
  thread_id: z.string(),
  title: z.string(),
  turns: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
})

export const indexedDocumentSchema = z.object({
  filename: z.string(),
  chunks: z.number(),
  indexed_at: z.string(),
  access: z.array(z.string()).default(['all']), // groups allowed to retrieve it
})

export const sessionUserSchema = z.object({
  username: z.string(),
  display_name: z.string(),
  role: z.enum(['employee', 'admin']),
  domains: z.array(z.string()),
  groups: z.array(z.string()),
})

export const sessionSchema = z.object({ access_token: z.string(), user: sessionUserSchema })

export const demoAccountSchema = sessionUserSchema.extend({ account: z.string() })

export type DomainConfig = z.infer<typeof domainConfigSchema>
export type DomainsResponse = z.infer<typeof domainsResponseSchema>
export type SourceUsed = z.infer<typeof sourceUsedSchema>
export type Citation = z.infer<typeof citationSchema>
export type ChatResponse = z.infer<typeof chatResponseSchema>
export type SupportStatus = ChatResponse['support_status']
export type Triage = z.infer<typeof triageSchema>
export type MemoryTurn = z.infer<typeof memoryTurnSchema>
export type Conversation = z.infer<typeof conversationSchema>
export type IndexedDocument = z.infer<typeof indexedDocumentSchema>
export type SessionUser = z.infer<typeof sessionUserSchema>
export type DemoAccount = z.infer<typeof demoAccountSchema>
