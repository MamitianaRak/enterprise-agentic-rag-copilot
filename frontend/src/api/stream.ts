// The agent's progress arrives as Server-Sent Events. EventSource only supports GET and
// axios does not stream response bodies in the browser, so this uses fetch directly.
import { API_BASE_URL, ApiError, authHeader, detailMessage, handleUnauthorized } from './http'
import { chatResponseSchema, type ChatResponse } from './schemas'

export type StreamEvent =
  | { event: 'start'; data: { thread_id: string } }
  | { event: 'step'; data: { line: string } }
  | { event: 'result'; data: ChatResponse }
  | { event: 'error'; data: { status: number; detail: string } }

/** Parse one SSE block ("event: x\ndata: {...}"). */
export function parseSseBlock(block: string): StreamEvent | null {
  let event = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  if (!data) return null
  const payload = JSON.parse(data)
  if (event === 'result') return { event, data: chatResponseSchema.parse(payload) }
  return { event, data: payload } as StreamEvent
}

export async function streamChat(
  domain: string,
  body: { question: string; thread_id: string },
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response
  try {
    res = await fetch(new URL(`${API_BASE_URL}/api/chat/${domain}/stream`, window.location.origin), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...authHeader() },
      body: JSON.stringify(body),
      signal,
    })
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err
    throw new ApiError(0, detailMessage(undefined, 0))
  }
  if (!res.ok || !res.body) {
    handleUnauthorized(res.status)
    const err = await res.json().catch(() => ({}))
    throw new ApiError(res.status, detailMessage(err.detail, res.status))
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    let boundary: number
    while ((boundary = buffer.indexOf('\n\n')) >= 0) {
      const event = parseSseBlock(buffer.slice(0, boundary))
      buffer = buffer.slice(boundary + 2)
      if (event) onEvent(event)
    }
  }
}
