<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, type ModelSettings, type User, type Workspace } from './api'

interface Message { role: 'user' | 'assistant'; text: string; meta?: string; citations?: { label: string; detail: string }[] }

const users = ref<User[]>([])
const activeUserId = ref(localStorage.getItem('demo-user') || 'sales-jkt-1')
const workspace = ref<Workspace>('operations')
const input = ref('')
const loading = ref(false)
const error = ref('')
const showSettings = ref(false)
const uploadOpen = ref(false)
const messages = ref<Message[]>([
  { role: 'assistant', text: 'Halo! Saya siap membantu mengecek order, komisi, stok, atau mencari informasi dari dokumen.' },
])
const models = reactive<ModelSettings>({
  database_planner: { provider: 'demo', model: 'deterministic-router' },
  database_answer: { provider: 'demo', model: 'template-id' },
  pdf_answer: { provider: 'demo', model: 'extractive-id' },
})
const upload = reactive({ file: null as File | null, visibility: 'internal', region: 'jakarta', status: '' })

const activeUser = computed(() => users.value.find((u) => u.id === activeUserId.value))
const canOperate = computed(() => activeUser.value?.role !== 'public')
const isAdmin = computed(() => activeUser.value?.role === 'admin')
const suggestions = computed(() => workspace.value === 'operations'
  ? ['Status order ORD-1001?', 'Berapa komisi bulan ini?', 'Stok barang tersedia?']
  : ['Apa kebijakan yang berlaku?', 'Ringkas informasi penting dari dokumen'])

onMounted(async () => {
  users.value = await api.users()
  await loadModels()
})

watch(activeUserId, async (id) => {
  localStorage.setItem('demo-user', id)
  if (id === 'public') workspace.value = 'public'
  else if (workspace.value === 'public') workspace.value = 'operations'
  await loadModels()
})

async function loadModels() {
  if (activeUserId.value === 'public') return
  try { Object.assign(models, await api.getModels(activeUserId.value)) } catch { /* role-safe fallback */ }
}

async function send(text = input.value) {
  if (!text.trim() || loading.value) return
  error.value = ''
  messages.value.push({ role: 'user', text })
  input.value = ''
  loading.value = true
  try {
    const result = await api.chat(activeUserId.value, workspace.value, text)
    messages.value.push({
      role: 'assistant', text: result.answer, citations: result.citations,
      meta: `${result.route} · ${result.provider}/${result.model}`,
    })
  } catch (e) { error.value = e instanceof Error ? e.message : 'Terjadi kesalahan' }
  finally { loading.value = false }
}

async function saveModels() {
  try {
    await api.saveModels(activeUserId.value, models)
    showSettings.value = false
  } catch (e) { error.value = e instanceof Error ? e.message : 'Gagal menyimpan' }
}

async function uploadPdf() {
  if (!upload.file) return
  upload.status = 'Mengindeks…'
  try {
    const result = await api.uploadPdf(activeUserId.value, upload.file, upload.visibility, upload.region)
    upload.status = `${result.filename} siap dicari (${result.chunks} potongan).`
  } catch (e) { upload.status = e instanceof Error ? e.message : 'Upload gagal' }
}
</script>

<template>
  <div class="shell">
    <aside>
      <div class="brand"><span class="brand-mark">A</span><div><strong>Aruna</strong><small>Knowledge Assistant</small></div></div>
      <nav>
        <button :class="{ active: workspace === 'operations' }" :disabled="!canOperate" @click="workspace = 'operations'"><span>⌁</span> Operasional</button>
        <button :class="{ active: workspace === 'knowledge' }" :disabled="!canOperate" @click="workspace = 'knowledge'"><span>▤</span> Dokumen internal</button>
        <button :class="{ active: workspace === 'public' }" @click="workspace = 'public'"><span>◎</span> Informasi publik</button>
      </nav>
      <div class="aside-bottom">
        <button v-if="canOperate" class="plain" @click="uploadOpen = !uploadOpen">＋ Tambah PDF</button>
        <button v-if="isAdmin" class="plain" @click="showSettings = true">⚙ Pengaturan model</button>
        <div class="security"><span>◆</span><div><strong>Akses terlindungi</strong><small>Data difilter oleh peran & wilayah</small></div></div>
      </div>
    </aside>

    <main>
      <header>
        <div><small>RUANG KERJA</small><h1>{{ workspace === 'operations' ? 'Asisten Operasional' : workspace === 'knowledge' ? 'Dokumen Internal' : 'Informasi Publik' }}</h1></div>
        <label class="persona"><span class="avatar">{{ activeUser?.name?.charAt(0) || '?' }}</span><select v-model="activeUserId"><option v-for="user in users" :key="user.id" :value="user.id">{{ user.name }}</option></select></label>
      </header>

      <section v-if="uploadOpen" class="upload-panel">
        <div><strong>Indeks PDF</strong><small>PDF teks akan dipotong dan hanya muncul untuk audience yang dipilih.</small></div>
        <input type="file" accept="application/pdf" @change="upload.file = ($event.target as HTMLInputElement).files?.[0] || null" />
        <select v-model="upload.visibility"><option value="internal">Semua internal</option><option value="region">Wilayah tertentu</option><option value="public">Publik</option></select>
        <input v-if="upload.visibility === 'region'" v-model="upload.region" placeholder="wilayah" />
        <button @click="uploadPdf">Unggah</button><small>{{ upload.status }}</small>
      </section>

      <section class="conversation">
        <div v-for="(message, index) in messages" :key="index" :class="['message', message.role]">
          <span v-if="message.role === 'assistant'" class="bot-icon">A</span>
          <div class="bubble"><p>{{ message.text }}</p><div v-if="message.citations?.length" class="citations"><span v-for="cite in message.citations" :key="cite.label + cite.detail">{{ cite.label }} · {{ cite.detail }}</span></div><small v-if="message.meta">{{ message.meta }}</small></div>
        </div>
        <div v-if="loading" class="message assistant"><span class="bot-icon">A</span><div class="bubble typing">● ● ●</div></div>
      </section>

      <footer>
        <div class="suggestions"><button v-for="item in suggestions" :key="item" @click="send(item)">{{ item }}</button></div>
        <form @submit.prevent="send()"><textarea v-model="input" rows="1" placeholder="Tanyakan sesuatu…" @keydown.enter.exact.prevent="send()"></textarea><button class="send" :disabled="loading || !input.trim()">↑</button></form>
        <p v-if="error" class="error">{{ error }}</p><small>Jawaban AI dapat keliru. Selalu verifikasi keputusan penting.</small>
      </footer>
    </main>

    <div v-if="showSettings" class="modal-backdrop" @click.self="showSettings = false">
      <section class="modal"><div class="modal-head"><div><small>ADMINISTRATOR</small><h2>Model per tugas</h2></div><button @click="showSettings = false">×</button></div>
        <p>Provider dan model bisa berbeda untuk setiap tahap. API key disimpan di backend.</p>
        <label v-for="(_, task) in models" :key="task"><span>{{ task.replaceAll('_', ' ') }}</span><select v-model="models[task].provider"><option>demo</option><option>ollama</option><option>openai</option><option>anthropic</option></select><input v-model="models[task].model" /></label>
        <div class="modal-actions"><button class="secondary" @click="showSettings = false">Batal</button><button @click="saveModels">Simpan konfigurasi</button></div>
      </section>
    </div>
  </div>
</template>

