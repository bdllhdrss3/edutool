const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001/api/v1'

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    credentials: 'include',
    ...options,
    headers: options.body instanceof FormData ? options.headers : { 'Content-Type': 'application/json', ...options.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail: unknown = body?.detail
    const missingRoute = response.status === 405 || (response.status === 404 && detail === 'Not Found')
    if (missingRoute && /^\/documents\/\d+\/quiz$/.test(path)) {
      throw new Error('Check Me is unavailable on the running backend. It may be an older version without the quiz route. Restart the updated backend and try again.')
    }
    if (missingRoute && options.method === 'DELETE') {
      throw new Error('This delete action is unavailable on the running backend. Restart the updated backend and try again. Nothing was deleted by this request.')
    }
    if (typeof detail === 'string' && detail.trim()) throw new Error(detail)
    if (Array.isArray(detail)) {
      const messages = detail.map(item => typeof item?.msg === 'string' ? item.msg : '').filter(Boolean)
      if (messages.length) throw new Error(messages.join(' '))
    }
    throw new Error(`Request failed (${response.status}). Please try again.`)
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

export type User = { id: number; username: string; has_recovery_code: boolean; recovery_code?: string }
export type DocumentLanguage = 'en' | 'ar' | 'sw'
export type DocumentSummary = { id: number; title: string; filename: string; page_count: number; language: DocumentLanguage; created_at: string }
export type DocumentDetail = DocumentSummary & { pages: { page_number: number; text: string }[] }
export type UploadResult = Pick<DocumentSummary, 'id' | 'title' | 'filename' | 'page_count'> & { existing: boolean }
export type Conversation = { id: number; title: string; document_id: number | null; updated_at: string }
export type Message = { role: 'user' | 'assistant'; content: string }
export type ChatResult = { conversation_id: number | null; reply: string }
export type QuizQuestion = { question: string; options: string[]; correct_index: number; explanation: string; source_page: number }
export type QuizResult = { questions: QuizQuestion[] }
