import { useParams } from 'react-router'
import { useAuthStore } from '@/stores/auth-store'
import { useDomains } from './queries'

/** The domains the signed-in user may use, and the one selected in the URL: /:domain/c/:threadId */
export function useCurrentDomain() {
  const { domain: domainName, threadId } = useParams()
  const { data } = useDomains()
  const allowed = useAuthStore((s) => s.user?.domains)
  const domains = (data?.domains ?? []).filter((d) => allowed?.includes(d.name))
  const domain = domains.find((d) => d.name === domainName)
  return { domains, domain, domainName: domainName ?? '', threadId, loaded: Boolean(data) }
}
