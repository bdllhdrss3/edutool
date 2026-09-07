import { test as base, expect, type Page } from '@playwright/test'
import type { Conversation, DocumentDetail, Message, QuizQuestion } from '../src/api'

export const documentTitle = 'Database foundations'
export const chatTitle = 'Understanding transactions'
const timestamp = '2026-01-15T12:00:00Z'
const paragraph = 'A transaction groups related changes into one reliable operation. Atomicity prevents partial updates, while isolation protects concurrent work. '

function makeDocument(id: number, title: string): DocumentDetail {
  return {
    id, title, filename: `study-notes-${id}.pdf`, page_count: 6, created_at: timestamp,
    pages: Array.from({ length: 6 }, (_, index) => ({
      page_number: index + 1,
      text: `Source page ${index + 1}.\n\n${paragraph.repeat(24)}`,
    })),
  }
}

export type ApiCall = { method: string; path: string; body: unknown }
export class MockApi {
  documents = [makeDocument(1, documentTitle), makeDocument(2, 'Networks and distributed systems — extended revision notes')]
  conversations: Conversation[] = [
    { id: 11, title: chatTitle, document_id: 1, updated_at: timestamp },
    { id: 12, title: 'Isolation and consistency', document_id: 1, updated_at: timestamp },
    { id: 21, title: 'Network revision', document_id: 2, updated_at: timestamp },
  ]
  messages: Message[] = Array.from({ length: 16 }, (_, index) => ({
    role: index % 2 ? 'assistant' : 'user', content: `Saved message ${index + 1}. ${paragraph.repeat(2)}`,
  }))
  calls: ApiCall[] = []
  unexpected: string[] = []
  failDeletes = false

  callsFor(method: string, path: string) {
    return this.calls.filter(call => call.method === method && call.path === path)
  }

  async install(page: Page, baseURL: string) {
    const appOrigin = new URL(baseURL).origin
    // One catch-all route is installed before goto. Only same-origin GET assets
    // may reach the network; fetch/XHR, API URLs, and mutations always terminate here.
    await page.route('**/*', async route => {
      const request = route.request()
      const url = new URL(request.url())
      const method = request.method()
      const isApi = url.pathname.startsWith('/api/') || ['fetch', 'xhr'].includes(request.resourceType())
      if (!isApi) {
        if (url.origin === appOrigin && method === 'GET') return route.continue()
        if (!['GET', 'HEAD'].includes(method)) this.unexpected.push(`${method} ${url.pathname}`)
        return route.abort('blockedbyclient')
      }
      const path = url.pathname.replace(/^\/api\/v1/, '')
      const headers = {
        'access-control-allow-origin': appOrigin,
        'access-control-allow-credentials': 'true',
        'access-control-allow-methods': 'GET, POST, DELETE, OPTIONS',
        'access-control-allow-headers': 'Content-Type',
      }
      const json = (body: unknown, status = 200) => route.fulfill({ status, headers, json: body })
      const empty = () => route.fulfill({ status: 204, headers })
      if (method === 'OPTIONS') return empty()
      const body = request.postData() ? request.postDataJSON() as unknown : null
      this.calls.push({ method, path, body })
      if (method === 'GET' && path === '/auth/me') return json({ id: 99, username: 'playwright-student' })
      if (method === 'GET' && path === '/documents') {
        return json(this.documents.map(({ pages: _pages, ...summary }) => summary))
      }
      if (method === 'GET' && path === '/conversations') return json(this.conversations)
      const docMatch = path.match(/^\/documents\/(\d+)$/)
      const chatMatch = path.match(/^\/conversations\/(\d+)$/)
      if (method === 'GET' && docMatch) {
        const document = this.documents.find(item => item.id === Number(docMatch[1]))
        return document ? json(document) : json({ detail: 'Mock document missing' }, 404)
      }
      if (method === 'GET' && chatMatch) {
        const chat = this.conversations.find(item => item.id === Number(chatMatch[1]))
        return chat ? json({ ...chat, messages: this.messages }) : json({ detail: 'Mock chat missing' }, 404)
      }
      if (method === 'DELETE' && (docMatch || chatMatch || path === '/documents' || path === '/conversations')) {
        if (this.failDeletes) return json({ detail: 'Mock deletion failed. Nothing was removed.' }, 500)
        if (path === '/documents') { this.documents = []; this.conversations = [] }
        else if (path === '/conversations') this.conversations = []
        else if (docMatch) {
          this.documents = this.documents.filter(item => item.id !== Number(docMatch[1]))
          this.conversations = this.conversations.filter(item => item.document_id !== Number(docMatch[1]))
        } else if (chatMatch) this.conversations = this.conversations.filter(item => item.id !== Number(chatMatch[1]))
        return empty()
      }
      if (method === 'POST' && /^\/documents\/\d+\/quiz$/.test(path)) {
        const payload = body as { page_numbers: number[]; question_count: number }
        const questions: QuizQuestion[] = Array.from({ length: 10 }, (_, index) => ({
          question: `Question ${index + 1}: Which property prevents a transaction from leaving partial changes?`,
          options: ['Atomicity keeps all changes together.', 'Isolation sorts records alphabetically.', 'Durability removes every backup.', 'Consistency allows partial updates.'],
          correct_index: 0,
          explanation: `Atomicity makes the entire transaction succeed or fail as one unit. ${paragraph.repeat(12)}`,
          source_page: payload.page_numbers[index % payload.page_numbers.length]!,
        }))
        return json({ questions })
      }
      if (method === 'POST' && path === '/chat') {
        const payload = body as { content: string; conversation_id?: number }
        return json({ conversation_id: payload.conversation_id || 11, reply: `Mock reply: ${payload.content}` })
      }
      this.unexpected.push(`${method} ${path}`)
      return json({ detail: `Unhandled mock: ${method} ${path}` }, 501)
    })
  }
}

export const test = base.extend<{ mockApi: MockApi }>({
  mockApi: [async ({ page, baseURL }, use, testInfo) => {
    const mock = new MockApi()
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await mock.install(page, baseURL!)
    await use(mock)
    await testInfo.attach('mock-api-calls', { body: JSON.stringify(mock.calls, null, 2), contentType: 'application/json' })
    expect(mock.unexpected, 'All API requests must be handled locally').toEqual([])
    expect(errors, 'No uncaught browser errors').toEqual([])
  }, { auto: true }],
})
export { expect }