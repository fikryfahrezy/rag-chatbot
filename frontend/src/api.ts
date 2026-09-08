export type Role = 'public' | 'sales' | 'manager' | 'admin'
export type Workspace = 'operations' | 'knowledge' | 'public'

export interface User {
  id: string
  name: string
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

export interface ModelChoice { provider: 'demo' | 'ollama' | 'openai' | 'anthropic'; model: string }
export type ModelSettings = Record<'database_planner' | 'database_answer' | 'pdf_answer', ModelChoice>

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
  getModels: (userId: string) => request<ModelSettings>('/api/models', userId),
  saveModels: (userId: string, settings: ModelSettings) => request<ModelSettings>('/api/models', userId, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings),
  }),
  uploadPdf: (userId: string, file: File, visibility: string, region: string) => {
    const data = new FormData()
    data.append('file', file)
    data.append('visibility', visibility)
    if (region) data.append('region', region)
    return request<{ filename: string; chunks: number }>('/api/documents', userId, { method: 'POST', body: data })
  },
}

