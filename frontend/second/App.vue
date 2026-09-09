<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  api, type Citation, type DatabaseTable, type DocumentRecord, type ModelSettings, type Provider, type RegisteredModel, type User, type Workspace,
} from '../src/api'

type Page = 'database' | 'pdf' | 'admin'
interface Message {
  role: 'user' | 'assistant'
  text: string
  meta?: string
  citations?: Citation[]
}

const pathPage = window.location.pathname.replace(/^\/+|\/+$/g, '')
const page: Page = pathPage === 'pdf' || pathPage === 'admin' ? pathPage : 'database'
const pageTitle = page === 'pdf' ? 'PDF chat' : page === 'admin' ? 'Admin' : 'Database chat'

const users = ref<User[]>([])
const activeUserId = ref('')
const input = ref('')
const messages = ref<Message[]>([])
const loading = ref(false)
const status = ref('')
const error = ref('')
const sourceOpen = ref(false)
const documents = ref<DocumentRecord[]>([])
const databaseTables = ref<DatabaseTable[]>([])
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const models = reactive<ModelSettings>({
  database_planner: { provider: 'ollama', model: '' },
  database_answer: { provider: 'ollama', model: '' },
  pdf_answer: { provider: 'ollama', model: '' },
})
const registeredModels = ref<RegisteredModel[]>([])
const availableModels = ref<string[]>([])
const modelStatus = ref('')
const discovering = ref(false)
const newModel = reactive<{ name: string; provider: Provider; model: string }>({ name: '', provider: 'ollama', model: '' })

const eligibleUsers = computed(() => users.value.filter((user) => {
  if (page === 'admin') return user.role === 'admin'
  if (page === 'pdf') return user.group === 'C' && user.role !== 'admin'
  return (user.group === 'A' || user.group === 'B') && user.role !== 'admin'
}))
const activeUser = computed(() => users.value.find((user) => user.id === activeUserId.value))
const workspace = computed<Workspace>(() => activeUser.value?.group === 'B' ? 'public' : page === 'pdf' ? 'knowledge' : 'operations')
const usedSources = computed(() => {
  const seen = new Set<string>()
  return messages.value.flatMap((message) => message.citations || []).filter((citation) => {
    const key = `${citation.label}\n${citation.detail}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})

function resetChat() {
  messages.value = []
  error.value = ''
}

onMounted(async () => {
  try {
    users.value = await api.users()
    activeUserId.value = eligibleUsers.value[0]?.id || ''
    if (page === 'admin') await loadAdmin()
    else {
      resetChat()
      if (page === 'pdf') documents.value = await api.documents(activeUserId.value)
      if (page === 'database') databaseTables.value = (await api.databaseSource(activeUserId.value)).tables
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Unable to load the application.'
  }
})

watch(() => newModel.provider, () => {
  newModel.model = ''
  availableModels.value = []
  if (page === 'admin' && activeUserId.value) discoverModels()
})

async function send(text = input.value) {
  if (!text.trim() || loading.value || !activeUserId.value) return
  messages.value.push({ role: 'user', text: text.trim() })
  input.value = ''
  error.value = ''
  loading.value = true
  status.value = 'Connecting…'
  let reply: Message | undefined
  try {
    await api.chatStream(activeUserId.value, workspace.value, text.trim(), (event) => {
      if (event.type === 'error') throw new Error(event.error)
      if (event.type === 'status') status.value = event.status
      if (event.type === 'delta') {
        if (!reply) {
          reply = { role: 'assistant', text: '' }
          messages.value.push(reply)
        }
        reply.text += event.delta
      }
      if (event.type === 'done') {
        if (!reply) {
          reply = { role: 'assistant', text: '' }
          messages.value.push(reply)
        }
        reply.citations = event.citations
        reply.meta = `${event.route} · ${event.provider}/${event.model}`
      }
    })
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'The request failed.'
  } finally {
    loading.value = false
    status.value = ''
  }
}

async function uploadPdf(event: Event) {
  const control = event.target as HTMLInputElement
  const file = control.files?.[0]
  if (!file || !activeUserId.value) return
  uploading.value = true
  error.value = ''
  try {
    const uploaded = await api.uploadPdf(activeUserId.value, file, 'internal', '')
    documents.value = [uploaded, ...documents.value.filter((document) => document.id !== uploaded.id)]
    sourceOpen.value = true
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Upload failed.'
  } finally {
    uploading.value = false
    control.value = ''
  }
}

function modelKey(model: { provider: Provider; model: string }) {
  return `${model.provider}\n${model.model}`
}

function assignModel(task: keyof ModelSettings, key: string) {
  const selected = registeredModels.value.find((model) => modelKey(model) === key)
  if (selected) models[task] = { provider: selected.provider, model: selected.model }
}

async function loadAdmin() {
  if (!activeUserId.value) return
  Object.assign(models, await api.getModels(activeUserId.value))
  registeredModels.value = await api.registeredModels(activeUserId.value)
  await discoverModels()
}

async function discoverModels() {
  discovering.value = true
  modelStatus.value = ''
  try {
    const result = await api.providerModels(activeUserId.value, newModel.provider)
    availableModels.value = result.models
    newModel.model = result.models[0] || ''
    if (!result.models.length) modelStatus.value = 'No models were found for this provider.'
  } catch (caught) {
    availableModels.value = []
    modelStatus.value = caught instanceof Error ? caught.message : 'Could not discover models.'
  } finally {
    discovering.value = false
  }
}

async function registerModel() {
  modelStatus.value = ''
  try {
    const saved = await api.registerModel(activeUserId.value, newModel)
    registeredModels.value.push(saved)
    newModel.name = ''
    modelStatus.value = 'Model added.'
  } catch (caught) {
    modelStatus.value = caught instanceof Error ? caught.message : 'Could not add model.'
  }
}

async function removeModel(model: RegisteredModel) {
  try {
    await api.deleteRegisteredModel(activeUserId.value, model.id)
    registeredModels.value = registeredModels.value.filter((item) => item.id !== model.id)
    modelStatus.value = 'Model removed.'
  } catch (caught) {
    modelStatus.value = caught instanceof Error ? caught.message : 'Could not remove model.'
  }
}

async function saveConfiguration() {
  try {
    await api.saveModels(activeUserId.value, models)
    modelStatus.value = 'Configuration saved.'
  } catch (caught) {
    modelStatus.value = caught instanceof Error ? caught.message : 'Could not save configuration.'
  }
}
</script>

<template>
  <div class="shell">
    <header>
      <a class="brand" href="/database"><span>A</span> Aruna</a>
      <strong class="page-title">{{ pageTitle }}</strong>
      <nav aria-label="Main navigation">
        <a href="/database" :aria-current="page === 'database' ? 'page' : undefined">Database</a>
        <a href="/pdf" :aria-current="page === 'pdf' ? 'page' : undefined">PDF</a>
        <a href="/admin" :aria-current="page === 'admin' ? 'page' : undefined">Admin</a>
      </nav>
    </header>

    <main :class="{ 'with-source': sourceOpen && page !== 'admin' }">
      <template v-if="page !== 'admin'">
        <div class="chat-layout">
          <div class="chat-column">
            <section class="chat" aria-live="polite">
              <div v-if="!messages.length && !loading" class="empty-state">
                <span>A</span>
                <p>{{ page === 'pdf' ? 'Ask about your documents.' : 'Ask about your data.' }}</p>
              </div>
              <article v-for="(message, index) in messages" :key="index" :class="message.role">
                <span>{{ message.role === 'assistant' ? 'A' : 'You' }}</span>
                <div><p>{{ message.text }}</p><small v-if="message.meta">{{ message.meta }}</small><div v-if="message.citations?.length" class="citations"><span v-for="citation in message.citations" :key="citation.label + citation.detail">{{ citation.label }} · {{ citation.detail }}</span></div></div>
              </article>
              <p v-if="loading" class="progress">{{ status || 'Thinking…' }}</p>
            </section>

            <section class="composer">
              <div class="composer-tools">
                <button class="source-toggle" :aria-expanded="sourceOpen" @click="sourceOpen = !sourceOpen">
                  {{ page === 'pdf' ? 'Documents' : 'Sources' }}
                </button>
              </div>
              <form @submit.prevent="send()">
                <input ref="fileInput" class="file-input" type="file" accept="application/pdf" @change="uploadPdf" />
                <button v-if="page === 'pdf'" type="button" class="attach" :disabled="uploading" :title="uploading ? 'Uploading PDF' : 'Upload PDF'" @click="fileInput?.click()">{{ uploading ? '…' : '+' }}</button>
                <textarea v-model="input" rows="1" :placeholder="page === 'pdf' ? 'Ask about a document…' : 'Ask about your data…'" @keydown.enter.exact.prevent="send()"></textarea>
                <button class="send-button" :disabled="loading || !input.trim()" aria-label="Send message">↑</button>
              </form>
              <p v-if="error" class="error">{{ error }}</p>
            </section>
          </div>

          <aside v-if="sourceOpen" class="source-panel" :class="{ database: page === 'database' }">
            <div class="source-head"><strong>{{ page === 'pdf' ? 'Documents' : 'Sources' }}</strong><button aria-label="Close sources" @click="sourceOpen = false">×</button></div>
            <template v-if="page === 'pdf'">
              <button class="upload-source" :disabled="uploading" @click="fileInput?.click()">{{ uploading ? 'Uploading…' : '+ Upload PDF' }}</button>
              <p v-if="!documents.length" class="source-empty">No PDFs uploaded yet.</p>
              <ul v-else><li v-for="document in documents" :key="document.id"><span class="file-mark">PDF</span><div><strong>{{ document.filename }}</strong><small>{{ document.chunks }} chunks · {{ document.visibility }}</small></div></li></ul>
            </template>
            <template v-else>
              <p v-if="!databaseTables.length" class="source-empty">No authorized table data.</p>
              <section v-for="table in databaseTables" v-else :key="table.name" class="data-table">
                <div><strong>{{ table.name }}</strong><small>{{ table.rows.length }} rows</small></div>
                <div class="table-scroll">
                  <table>
                    <thead><tr><th v-for="column in table.columns" :key="column">{{ column }}</th></tr></thead>
                    <tbody>
                      <tr v-for="(row, rowIndex) in table.rows" :key="rowIndex"><td v-for="column in table.columns" :key="column">{{ row[column] }}</td></tr>
                      <tr v-if="!table.rows.length"><td :colspan="table.columns.length">No authorized rows</td></tr>
                    </tbody>
                  </table>
                </div>
              </section>
              <template v-if="usedSources.length"><small class="source-label used-label">Used in this chat</small><ul><li v-for="source in usedSources" :key="source.label + source.detail"><span class="table-mark">✓</span><div><strong>{{ source.label }}</strong><small>{{ source.detail }}</small></div></li></ul></template>
            </template>
          </aside>
        </div>
      </template>

      <section v-else class="admin-grid">
        <div class="admin-heading"><small>Configuration</small><h1>Model settings</h1></div>
        <div class="panel assignments">
          <div class="panel-title"><div><small>Task routing</small><h2>Model assignments</h2></div><button @click="saveConfiguration">Save</button></div>
          <label v-for="(_, task) in models" :key="task"><span>{{ task.replaceAll('_', ' ') }}</span><select :value="modelKey(models[task])" @change="assignModel(task, ($event.target as HTMLSelectElement).value)"><option v-for="model in registeredModels" :key="model.id" :value="modelKey(model)">{{ model.name }} · {{ model.provider }}/{{ model.model }}</option></select></label>
        </div>
        <div class="panel registry">
          <div class="panel-title"><div><small>Providers</small><h2>Registered models</h2></div></div>
          <form @submit.prevent="registerModel"><input v-model="newModel.name" required placeholder="Display name" /><select v-model="newModel.provider"><option>ollama</option><option>openai</option><option>anthropic</option></select><select v-model="newModel.model" required :disabled="discovering"><option value="" disabled>{{ discovering ? 'Loading…' : 'Select model' }}</option><option v-for="model in availableModels" :key="model">{{ model }}</option></select><button>Add</button></form>
          <ul><li v-for="model in registeredModels" :key="model.id"><span><strong>{{ model.name }}</strong><small>{{ model.provider }}/{{ model.model }}</small></span><button title="Remove model" @click="removeModel(model)">×</button></li></ul>
          <p v-if="modelStatus" class="notice">{{ modelStatus }}</p>
          <p v-if="error" class="error">{{ error }}</p>
        </div>
      </section>
    </main>
  </div>
</template>
