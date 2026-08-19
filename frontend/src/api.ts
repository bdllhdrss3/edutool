const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001/api/v1'

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    credentials: 'include',
    ...options,
    headers: options.body instanceof FormData ? options.headers : { 'Content-Type': 'application/json', ...options.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(body.detail || 'Request failed')
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

export type User = { id: number; username: string }
export type DocumentSummary = { id: number; title: string; filename: string; page_count: number; created_at: string }
export type DocumentDetail = DocumentSummary & { pages: { page_number: number; text: string }[] }
export type Conversation = { id: number; title: string; document_id: number | null; updated_at: string }
export type Message = { role: 'user' | 'assistant'; content: string }
