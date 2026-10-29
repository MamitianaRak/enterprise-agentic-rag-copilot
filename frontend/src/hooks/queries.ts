import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/api/endpoints'

export const queryKeys = {
  domains: ['domains'] as const,
  conversations: (domain: string) => ['conversations', domain] as const,
  history: (domain: string, threadId: string) => ['history', domain, threadId] as const,
  documents: (domain: string) => ['documents', domain] as const,
}

export function useDemoAccounts() {
  return useQuery({ queryKey: ['demo-accounts'], queryFn: api.demoAccounts, staleTime: Infinity })
}

export function useDomains() {
  return useQuery({ queryKey: queryKeys.domains, queryFn: api.domains, staleTime: Infinity })
}

export function useConversations(domain: string) {
  return useQuery({ queryKey: queryKeys.conversations(domain), queryFn: () => api.conversations(domain) })
}

export function useHistory(domain: string, threadId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.history(domain, threadId ?? ''),
    queryFn: () => api.history(domain, threadId!),
    enabled: Boolean(threadId),
  })
}

export function useDeleteConversation(domain: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (threadId: string) => api.deleteConversation(domain, threadId),
    onSuccess: (_, threadId) => {
      queryClient.removeQueries({ queryKey: queryKeys.history(domain, threadId) })
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations(domain) })
      toast.success('Conversation deleted')
    },
    onError: (err) => toast.error(err.message),
  })
}

export function useDocuments(domain: string, enabled = true) {
  return useQuery({ queryKey: queryKeys.documents(domain), queryFn: () => api.documents(domain), enabled })
}

export function useUploadDocument(domain: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ file, access }: { file: File; access: string }) => api.uploadDocument(domain, file, access),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.documents(domain) })
      toast.success(`Indexed ${data.file}`, { description: `${data.chunks} chunks added to the knowledge base.` })
    },
    onError: (err) => toast.error('Upload failed', { description: err.message }),
  })
}

export function useDeleteDocument(domain: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ filename }: { filename: string }) => api.deleteDocument(domain, filename),
    onSuccess: (_, { filename }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.documents(domain) })
      toast.success(`Removed ${filename}`)
    },
    onError: (err) => toast.error('Delete failed', { description: err.message }),
  })
}
