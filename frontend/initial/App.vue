<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import {
  api, type Group, type ModelSettings, type Provider, type RegisteredModel, type User, type Workspace,
} from '../src/api'

interface Message {
  role: 'user' | 'assistant'
  text: string
  meta?: string
  citations?: { label: string; detail: string }[]
}

const groups: { id: Group; label: string; title: string; description: string }[] = [
  {
    id: 'A',
    label: 'Group A',
    title: 'Operational Assistant',
    description: 'Ask about order status, commissions, and inventory. Results are restricted by sales ownership and manager region.',
  },
  {
    id: 'B',
    label: 'Group B',
    title: 'Public Assistant',
    description: 'A public-facing chatbot that only exposes approved public information and documents.',
  },
  {
    id: 'C',
    label: 'Group C',
    title: 'Document Assistant',
    description: 'Search internal PDF knowledge with document visibility and regional access controls.',
  },
]

const users = ref<User[]>([])
const activeUserId = ref(localStorage.getItem('demo-user') || '')
const savedAdminGroup = localStorage.getItem('admin-group')
const adminGroup = ref<Group>(savedAdminGroup === 'A' || savedAdminGroup === 'B' || savedAdminGroup === 'C' ? savedAdminGroup : 'C')
const input = ref('')
const loading = ref(false)
const streamStatus = ref('')
const error = ref('')
const showSettings = ref(false)
const uploadOpen = ref(false)
const messages = ref<Message[]>([])
const registeredModels = ref<RegisteredModel[]>([])
const availableProviderModels = ref<string[]>([])
const discoveringModels = ref(false)
const modelStatus = ref('')
const newModel = reactive<{ name: string; provider: Provider; model: string }>({ name: '', provider: 'ollama', model: '' })
const models = reactive<ModelSettings>({
  database_planner: { provider: 'ollama', model: 'qwen3.5:4b-q4_K_M' },
  database_answer: { provider: 'ollama', model: 'qwen3.5:4b-q4_K_M' },
  pdf_answer: { provider: 'ollama', model: 'qwen3.5:4b-q4_K_M' },
})
const upload = reactive<{
  file: File | null
  visibility: 'internal' | 'region'
  region: string
  status: string
}>({ file: null, visibility: 'internal', region: 'jakarta', status: '' })

const activeUser = computed(() => users.value.find((user) => user.id === activeUserId.value))
const regions = computed(() => [...new Set(users.value.flatMap((user) => user.region ? [user.region] : []))].sort())
const isAdmin = computed(() => activeUser.value?.role === 'admin')
const activeGroup = computed<Group>(() => activeUser.value?.group === 'ALL' ? adminGroup.value : (activeUser.value?.group || 'A'))
const group = computed(() => groups.find((item) => item.id === activeGroup.value) || groups[0])
const workspace = computed<Workspace>(() => ({ A: 'operations', B: 'public', C: 'knowledge' })[activeGroup.value] as Workspace)
const canUpload = computed(() => activeGroup.value === 'C' && activeUser.value?.role !== 'public')
const suggestions = computed(() => {
  if (activeGroup.value === 'A') return ['Status order ORD-1001?', 'Berapa komisi bulan ini?', 'Stok barang tersedia?']
  if (activeGroup.value === 'B') return ['Produk apa yang tersedia?', 'Informasi publik apa yang tersedia?']
  return ['Apa kebijakan yang berlaku?', 'Ringkas informasi penting dari dokumen']
})
const awaitingFirstToken = computed(() => loading.value && messages.value.at(-1)?.role === 'user')

function welcomeMessage(): Message {
  return { role: 'assistant', text: group.value.title + ' siap digunakan. ' + group.value.description }
}

function resetConversation() {
  error.value = ''
  messages.value = [welcomeMessage()]
}

onMounted(async () => {
  try {
    users.value = await api.users()
    const savedUserIsValid = users.value.some((user) => user.id === activeUserId.value)
    activeUserId.value = savedUserIsValid ? activeUserId.value : (users.value[0]?.id || '')
    if (!regions.value.includes(upload.region)) upload.region = regions.value[0] || ''
    resetConversation()
    await loadModels()
  } catch (e) {
    error.value = e instanceof Error
      ? 'Tidak dapat memuat profil akses: ' + e.message
      : 'Tidak dapat memuat profil akses. Pastikan backend berjalan.'
  }
})

watch(activeUserId, async (id, previousId) => {
  if (!id) return
  localStorage.setItem('demo-user', id)
  uploadOpen.value = false
  if (previousId) resetConversation()
  await loadModels()
})

watch(adminGroup, (value) => {
  localStorage.setItem('admin-group', value)
  uploadOpen.value = false
  if (isAdmin.value) resetConversation()
})

watch(() => newModel.provider, () => {
  newModel.model = ''
  availableProviderModels.value = []
  if (showSettings.value) discoverProviderModels()
})

async function loadModels() {
  if (!activeUserId.value || (activeGroup.value === 'B' && !isAdmin.value)) return
  try {
    Object.assign(models, await api.getModels(activeUserId.value))
    if (isAdmin.value) registeredModels.value = await api.registeredModels(activeUserId.value)
  } catch {
    // Model configuration is only editable by the administrator.
  }
}

function modelKey(model: { provider: Provider; model: string }) {
  return model.provider + '\n' + model.model
}

function selectTaskModel(task: keyof ModelSettings, key: string) {
  const selected = registeredModels.value.find((item) => modelKey(item) === key)
  if (selected) models[task] = { provider: selected.provider, model: selected.model }
}

async function registerModel() {
  modelStatus.value = ''
  try {
    const registered = await api.registerModel(activeUserId.value, newModel)
    registeredModels.value.push(registered)
    registeredModels.value.sort((left, right) => left.name.localeCompare(right.name))
    newModel.name = ''
    newModel.model = ''
    modelStatus.value = 'Model registered.'
  } catch (e) {
    modelStatus.value = e instanceof Error ? e.message : 'Failed to register model'
  }
}

async function discoverProviderModels() {
  discoveringModels.value = true
  modelStatus.value = ''
  try {
    const result = await api.providerModels(activeUserId.value, newModel.provider)
    availableProviderModels.value = result.models
    if (!result.models.includes(newModel.model)) newModel.model = result.models[0] || ''
    if (!result.models.length) modelStatus.value = 'No models are available from this provider.'
  } catch (e) {
    availableProviderModels.value = []
    newModel.model = ''
    modelStatus.value = e instanceof Error ? e.message : 'Failed to fetch provider models'
  } finally {
    discoveringModels.value = false
  }
}

async function deleteRegisteredModel(model: RegisteredModel) {
  modelStatus.value = ''
  try {
    await api.deleteRegisteredModel(activeUserId.value, model.id)
    registeredModels.value = registeredModels.value.filter((item) => item.id !== model.id)
    modelStatus.value = 'Model removed.'
  } catch (e) {
    modelStatus.value = e instanceof Error ? e.message : 'Failed to remove model'
  }
}

async function openSettings() {
  await loadModels()
  modelStatus.value = ''
  showSettings.value = true
  await discoverProviderModels()
}

async function send(text = input.value) {
  if (!text.trim() || loading.value || !activeUserId.value) return
  error.value = ''
  messages.value.push({ role: 'user', text })
  input.value = ''
  loading.value = true
  streamStatus.value = 'Connecting…'
  let assistantIndex = -1
  const ensureAssistant = () => {
    if (assistantIndex < 0) {
      messages.value.push({ role: 'assistant', text: '' })
      assistantIndex = messages.value.length - 1
    }
    return messages.value[assistantIndex]
  }
  try {
    await api.chatStream(activeUserId.value, workspace.value, text, (event) => {
      if (event.type === 'error') throw new Error(event.error)
      if (event.type === 'status') {
        streamStatus.value = event.status
        return
      }
      const assistant = ensureAssistant()
      if (event.type === 'delta') assistant.text += event.delta
      if (event.type === 'done') {
        assistant.citations = event.citations
        assistant.meta = event.route + ' · ' + event.provider + '/' + event.model
      }
    })
  } catch (e) {
    if (assistantIndex >= 0 && !messages.value[assistantIndex].text) messages.value.splice(assistantIndex, 1)
    error.value = e instanceof Error ? e.message : 'Terjadi kesalahan'
  } finally {
    loading.value = false
    streamStatus.value = ''
  }
}

async function saveModels() {
  try {
    await api.saveModels(activeUserId.value, models)
    showSettings.value = false
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Gagal menyimpan'
  }
}

async function uploadPdf() {
  if (!upload.file) return
  upload.status = 'Mengindeks…'
  try {
    const result = await api.uploadPdf(activeUserId.value, upload.file, upload.visibility, upload.region)
    upload.status = result.filename + ' siap dicari (' + result.chunks + ' potongan).'
  } catch (e) {
    upload.status = e instanceof Error ? e.message : 'Upload gagal'
  }
}
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark">A</span>
        <div><strong>Aruna</strong><small>Knowledge Assistant</small></div>
      </div>
      <div class="experience">
        <span>Current experience</span>
        <select v-if="isAdmin" v-model="adminGroup" aria-label="Administrator experience">
          <option v-for="item in groups" :key="item.id" :value="item.id">{{ item.label }} · {{ item.title }}</option>
        </select>
        <strong v-else>{{ group.label }} · {{ group.title }}</strong>
      </div>
      <div class="header-actions">
        <button v-if="isAdmin" class="secondary-action" @click="openSettings">⚙ Model settings</button>
        <label class="persona">
          <span>User</span>
          <select v-model="activeUserId" :disabled="users.length <= 1">
            <option v-for="user in users" :key="user.id" :value="user.id">{{ user.group === 'ALL' ? 'All Groups' : 'Group ' + user.group }} · {{ user.name }}</option>
          </select>
        </label>
      </div>
    </header>

    <main>
      <section class="conversation">
        <div v-for="(message, index) in messages" :key="index" :class="['message', message.role]">
          <span v-if="message.role === 'assistant'" class="bot-icon">A</span>
          <div class="bubble">
            <p>{{ message.text }}</p>
            <div v-if="message.citations?.length" class="citations">
              <span v-for="cite in message.citations" :key="cite.label + cite.detail">{{ cite.label }} · {{ cite.detail }}</span>
            </div>
            <small v-if="message.meta">{{ message.meta }}</small>
          </div>
        </div>
        <div v-if="awaitingFirstToken" class="message assistant"><span class="bot-icon">A</span><div class="bubble typing">{{ streamStatus || '● ● ●' }}</div></div>
      </section>

      <footer>
        <section v-if="uploadOpen" class="upload-panel">
          <div><strong>Add a PDF to Group C</strong><small>Choose who is allowed to retrieve content from this document.</small></div>
          <input type="file" accept="application/pdf" @change="upload.file = ($event.target as HTMLInputElement).files?.[0] || null" />
          <select v-model="upload.visibility">
            <option value="internal">All Group C users</option>
            <option value="region">Group C users in a specific region</option>
          </select>
          <select v-if="upload.visibility === 'region'" v-model="upload.region" aria-label="Document region">
            <option v-for="region in regions" :key="region" :value="region">{{ region.charAt(0).toUpperCase() + region.slice(1) }}</option>
          </select>
          <button type="button" @click="uploadPdf">Upload</button>
          <small>{{ upload.status }}</small>
        </section>
        <div class="suggestions"><button v-for="item in suggestions" :key="item" @click="send(item)">{{ item }}</button></div>
        <form @submit.prevent="send()">
          <button v-if="canUpload" type="button" class="attach-button" :class="{ active: uploadOpen }" @click="uploadOpen = !uploadOpen">＋ PDF</button>
          <textarea v-model="input" rows="1" :placeholder="'Ask Group ' + activeGroup + '…'" @keydown.enter.exact.prevent="send()"></textarea>
          <button class="send" :disabled="loading || !input.trim()">↑</button>
        </form>
        <p v-if="error" class="error">{{ error }}</p>
        <small>AI responses may be inaccurate. Verify important decisions against the source system.</small>
      </footer>
    </main>

    <div v-if="showSettings" class="modal-backdrop" @click.self="showSettings = false">
      <section class="modal">
        <div class="modal-head"><div><small>ADMINISTRATOR</small><h2>Model per task</h2></div><button @click="showSettings = false">×</button></div>
        <p>Register models once, then assign an existing model to each processing stage.</p>
        <label v-for="(_, task) in models" :key="task">
          <span>{{ task.replaceAll('_', ' ') }}</span>
          <select :value="modelKey(models[task])" @change="selectTaskModel(task, ($event.target as HTMLSelectElement).value)">
            <option v-for="item in registeredModels" :key="item.id" :value="modelKey(item)">{{ item.name }} · {{ item.provider }}/{{ item.model }}</option>
          </select>
        </label>
        <section class="model-registry">
          <div><strong>Registered models</strong><small>API keys remain in the backend environment.</small></div>
          <form class="model-form" @submit.prevent="registerModel">
            <input v-model="newModel.name" required maxlength="80" placeholder="Display name" />
            <select v-model="newModel.provider"><option>ollama</option><option>openai</option><option>anthropic</option></select>
            <select v-model="newModel.model" required :disabled="discoveringModels || !availableProviderModels.length">
              <option value="" disabled>{{ discoveringModels ? 'Loading models…' : 'Select an available model' }}</option>
              <option v-for="model in availableProviderModels" :key="model" :value="model">{{ model }}</option>
            </select>
            <button type="button" :disabled="discoveringModels" @click="discoverProviderModels">Refresh</button>
            <button type="submit" :disabled="discoveringModels || !newModel.model">Add</button>
          </form>
          <div class="registered-list">
            <div v-for="item in registeredModels" :key="item.id">
              <span><strong>{{ item.name }}</strong><small>{{ item.provider }}/{{ item.model }}</small></span>
              <button type="button" title="Remove registered model" @click="deleteRegisteredModel(item)">×</button>
            </div>
          </div>
          <p v-if="modelStatus" class="model-status">{{ modelStatus }}</p>
        </section>
        <div class="modal-actions"><button class="secondary" @click="showSettings = false">Cancel</button><button @click="saveModels">Save configuration</button></div>
      </section>
    </div>
  </div>
</template>
