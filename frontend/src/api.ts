export type Group = 'A' | 'B' | 'C'
export type UserGroup = Group | 'ALL'
export type Role = 'public' | 'sales' | 'manager' | 'employee' | 'admin'
export type Workspace = 'operations' | 'knowledge' | 'public'
export type Provider = 'ollama' | 'openai' | 'anthropic'

export interface User {
  id: string
  name: string
  group: UserGroup
  role: Role
  region?: string
}

export interface Citation { label: string; detail: string }
export interface ChatResponse {
  answer: string
  citations: Citation[]
  provider: string
  model: string
  route: string
}
export type ChatStreamEvent =
  | { type: 'status'; status: string }
  | { type: 'delta'; delta: string }
  | { type: 'done'; citations: Citation[]; provider: string; model: string; route: string }
  | { type: 'error'; error: string }

export interface ModelChoice { provider: Provider; model: string }
export type ModelSettings = Record<'database_planner' | 'database_answer' | 'pdf_answer', ModelChoice>
export interface RegisteredModel { id: number; name: string; provider: Provider; model: string }
export interface RegisteredModelCreate { name: string; provider: Provider; model: string }
export interface DocumentRecord {
  id: number
  filename: string
  visibility: 'internal' | 'region'
  region?: string | null
  chunks: number
}
export interface DatabaseTable {
  name: string
  columns: string[]
  rows: Record<string, string | number | null>[]
}

const baseUrl = import.meta.env.VITE_API_URL || ''

async function request<T>(path: string, userId: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: { 'X-Demo-User': userId, ...options?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  return response.json()
}

export const api = {
  users: () => request<User[]>('/api/users', 'public'),
  chat: (userId: string, workspace: Workspace, message: string) => request<ChatResponse>('/api/chat', userId, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ workspace, message }),
  }),
  chatStream: async (
    userId: string,
    workspace: Workspace,
    message: string,
    onEvent: (event: ChatStreamEvent) => void,
  ) => {
    const response = await fetch(`${baseUrl}/api/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Demo-User': userId },
      body: JSON.stringify({ workspace, message }),
    })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(body.detail || `Request failed (${response.status})`)
    }
    if (!response.body) throw new Error('Streaming is not supported by this browser')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (line.trim()) onEvent(JSON.parse(line) as ChatStreamEvent)
      }
      if (done) break
    }
    if (buffer.trim()) onEvent(JSON.parse(buffer) as ChatStreamEvent)
  },
  getModels: (userId: string) => request<ModelSettings>('/api/models', userId),
  saveModels: (userId: string, settings: ModelSettings) => request<ModelSettings>('/api/models', userId, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings),
  }),
  registeredModels: (userId: string) => request<RegisteredModel[]>('/api/registered-models', userId),
  providerModels: (userId: string, provider: Provider) => request<{ provider: Provider; models: string[] }>(`/api/provider-models/${provider}`, userId),
  registerModel: (userId: string, model: RegisteredModelCreate) => request<RegisteredModel>('/api/registered-models', userId, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(model),
  }),
  deleteRegisteredModel: (userId: string, modelId: number) => request<{ deleted: number }>(`/api/registered-models/${modelId}`, userId, {
    method: 'DELETE',
  }),
  documents: (userId: string) => request<DocumentRecord[]>('/api/documents', userId),
  databaseSource: (userId: string) => request<{ tables: DatabaseTable[] }>('/api/database-source', userId),
  uploadPdf: (userId: string, file: File, visibility: 'internal' | 'region', region: string) => {
    const data = new FormData()
    data.append('file', file)
    data.append('visibility', visibility)
    if (visibility === 'region') data.append('region', region)
    return request<DocumentRecord>('/api/documents', userId, { method: 'POST', body: data })
  },
}
