<script setup>
import { ref, onMounted } from 'vue'

const messages = ref([])
const loading = ref(false)
const sidebarOpen = ref(true)
const currentFile = ref(null)
const webMode = ref(false)
const stats = ref({ documentos_indexados: 0, indice_denso_carregado: false })
const uploadName = ref('')

async function ask(query) {
  if (!query.trim()) return
  loading.value = true
  messages.value.push({ role: 'user', content: query })

  const body = { query, file: currentFile.value, web: webMode.value }
  const res = await fetch('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  const data = await res.json()
  loading.value = false
  messages.value.push({
    role: 'oracle',
    content: data.answer,
    confidence: data.confidence,
    decision: data.decision,
    source: data.source,
    chunks: data.chunks || [],
    time: data.time_ms
  })
  if (currentFile.value) currentFile.value = null
}

async function uploadFile(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch('/api/upload', { method: 'POST', body: form })
  const data = await res.json()
  uploadName.value = file.name
  currentFile.value = data.path
}

async function loadStats() {
  const res = await fetch('/api/stats')
  stats.value = await res.json()
}

function clearChat() {
  messages.value = []
}

function example(q) {
  ask(q)
}

onMounted(loadStats)
</script>

<template>
  <div class="flex h-screen bg-surface overflow-hidden">
    <!-- Particles -->
    <div class="fixed inset-0 pointer-events-none overflow-hidden z-0">
      <div v-for="i in 20" :key="i" class="absolute rounded-full"
        :style="{
          width: (Math.random() * 3 + 1) + 'px',
          height: (Math.random() * 3 + 1) + 'px',
          left: Math.random() * 100 + '%',
          background: ['rgba(99,102,241,0.4)', 'rgba(6,182,212,0.4)', 'rgba(168,85,247,0.3)'][i % 3],
          animation: `float-particle ${Math.random() * 15 + 10}s linear infinite`,
          animationDelay: (Math.random() * 10) + 's'
        }">
      </div>
    </div>

    <!-- Sidebar -->
    <aside :class="[
      'relative z-10 flex flex-col border-r border-white/5 transition-all duration-300 bg-surface-2/50 backdrop-blur-xl',
      sidebarOpen ? 'w-72' : 'w-0 overflow-hidden'
    ]">
      <div class="flex-1 overflow-y-auto p-4 space-y-5">
        <!-- Status -->
        <div class="glass rounded-xl p-3">
          <div class="flex items-center gap-2 text-xs text-text-muted uppercase tracking-wider mb-2">
            <span class="w-2 h-2 rounded-full bg-success animate-pulse"></span>
            Sistema
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-text">Online</span>
            <span class="text-sm font-mono text-primary">{{ stats.documentos_indexados }} chunks</span>
          </div>
        </div>

        <!-- Upload -->
        <div class="glass rounded-xl p-3">
          <div class="text-xs text-text-muted uppercase tracking-wider mb-2">Arquivo</div>
          <label class="flex flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-white/10 p-4 cursor-pointer hover:border-primary/40 transition-colors">
            <svg class="w-5 h-5 text-text-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg>
            <span class="text-xs text-text-dim">PDF, TXT, CSV, HTML</span>
            <input type="file" accept=".pdf,.txt,.md,.csv,.html,.htm" class="hidden" @change="e => e.target.files[0] && uploadFile(e.target.files[0])">
          </label>
          <div v-if="uploadName" class="mt-2 flex items-center gap-1.5 text-xs text-secondary">
            <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
            {{ uploadName }}
          </div>
        </div>

        <!-- Web toggle -->
        <div class="glass rounded-xl p-3">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <svg class="w-4 h-4 text-text-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>
              <span class="text-sm text-text">Busca Web</span>
            </div>
            <button @click="webMode = !webMode" :class="['relative inline-flex h-5 w-9 items-center rounded-full transition-colors', webMode ? 'bg-primary' : 'bg-white/10']">
              <span :class="['inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform', webMode ? 'translate-x-4.5' : 'translate-x-1']"></span>
            </button>
          </div>
        </div>

        <!-- Actions -->
        <div class="glass rounded-xl p-3 space-y-2">
          <div class="text-xs text-text-muted uppercase tracking-wider mb-1">Acoes</div>
          <button @click="loadStats" class="btn-secondary w-full flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/><line x1="2" y1="20" x2="22" y2="20"/></svg>
            Estatisticas
          </button>
          <button @click="clearChat" class="btn-secondary w-full flex items-center gap-2">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
            Limpar Conversa
          </button>
        </div>

        <!-- Examples -->
        <div class="glass rounded-xl p-3">
          <div class="text-xs text-text-muted uppercase tracking-wider mb-2">Exemplos</div>
          <div class="space-y-1.5">
            <button v-for="ex in ['Qual o faturamento total?','Liste os produtos vendidos','Explique as regras tributarias']" :key="ex" @click="example(ex)" class="btn-secondary w-full text-left text-xs flex items-center gap-2">
              <svg class="w-3.5 h-3.5 text-warning flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path d="M9 18h6"/><path d="M10 22h4"/><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0018 8 6 6 0 006 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 018.91 14"/></svg>
              {{ ex }}
            </button>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="p-4 border-t border-white/5">
        <div class="flex items-center gap-2 text-xs text-text-dim">
          <svg class="w-3.5 h-3.5 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/></svg>
          CPU Inference
          <span class="text-white/10 mx-1">|</span>
          Self-RAG
        </div>
      </div>
    </aside>

    <!-- Toggle sidebar button -->
    <button @click="sidebarOpen = !sidebarOpen" class="fixed top-4 left-4 z-20 glass rounded-lg p-2 hover:bg-white/5 transition-colors" :style="{ left: sidebarOpen ? '17rem' : '0.5rem' }">
      <svg class="w-4 h-4 text-text-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path v-if="sidebarOpen" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 19l-7-7 7-7"/>
        <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 5l7 7-7 7"/>
      </svg>
    </button>

    <!-- Main -->
    <main class="flex-1 flex flex-col relative z-10 min-w-0">
      <!-- Header -->
      <header class="flex items-center justify-center py-6 px-4 border-b border-white/5">
        <div class="text-center">
          <h1 class="text-2xl font-bold gradient-text tracking-tight animate-glow">ORACULO RAG</h1>
          <p class="text-xs text-text-dim mt-0.5">consulta inteligente com self-rag</p>
        </div>
      </header>

      <!-- Messages -->
      <div class="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        <div v-if="messages.length === 0" class="flex flex-col items-center justify-center h-full text-center px-8">
          <svg class="w-12 h-12 text-text-dim mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <h2 class="text-lg font-medium text-text-muted mb-1">Faca uma pergunta</h2>
          <p class="text-sm text-text-dim max-w-md">Envie um arquivo ou use documentos indexados. O Oraculo usa Self-RAG para decidir como responder.</p>
          <div class="flex gap-2 mt-4">
            <span class="tag tag-primary">PDF</span>
            <span class="tag tag-success">TXT</span>
            <span class="tag tag-warning">CSV</span>
            <span class="tag tag-primary">SQL</span>
            <span class="tag tag-success">Web</span>
          </div>
        </div>

        <template v-for="(msg, i) in messages" :key="i">
          <!-- User -->
          <div v-if="msg.role === 'user'" class="flex justify-end animate-slide-up">
            <div class="max-w-[80%] glass rounded-2xl rounded-br-md px-4 py-3">
              <div class="flex items-center gap-2 mb-1">
                <svg class="w-3.5 h-3.5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                <span class="text-xs font-medium text-text-muted">Voce</span>
              </div>
              <p class="text-sm text-text leading-relaxed whitespace-pre-wrap">{{ msg.content }}</p>
            </div>
          </div>

          <!-- Oracle -->
          <div v-else class="animate-slide-up">
            <div class="max-w-[85%] glass gradient-border rounded-2xl rounded-bl-md px-4 py-3">
              <div class="flex items-center gap-2 mb-2">
                <svg class="w-4 h-4 text-secondary" fill="none" viewBox="0 0 24 24" stroke="currentColor"><circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 019 9" stroke="currentColor"/><circle cx="12" cy="12" r="3" fill="currentColor"/></svg>
                <span class="text-xs font-medium text-text-muted">Oraculo</span>
                <span :class="['tag', msg.confidence >= 0.6 ? 'tag-success' : msg.confidence >= 0.4 ? 'tag-warning' : 'tag-error']">
                  <svg v-if="msg.confidence >= 0.6" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                  <svg v-else-if="msg.confidence >= 0.4" class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                  <svg v-else class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                  {{ { '[Supported]': 'Suportado', '[Partially]': 'Parcial', '[No Support]': 'Nao encontrado' }[msg.decision] || msg.decision }}
                </span>
                <span class="text-xs text-text-dim">Confianca: {{ Math.round(msg.confidence * 100) }}%</span>
              </div>
              <p class="text-sm text-text leading-relaxed whitespace-pre-wrap">{{ msg.content }}</p>
              <div v-if="msg.chunks && msg.chunks.length" class="mt-2 pt-2 border-t border-white/5">
                <div class="text-xs text-text-dim mb-1">Fontes:</div>
                <div v-for="(chunk, ci) in msg.chunks.slice(0,3)" :key="ci" class="flex items-center gap-1.5 text-xs text-text-muted mb-0.5">
                  <svg class="w-3 h-3 text-text-dim flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                  {{ chunk.source }} ({{ Math.round(chunk.score * 100) }}%)
                </div>
              </div>
              <div v-if="msg.time" class="mt-1 text-xs text-text-dim/50">processado em {{ msg.time }}ms</div>
            </div>
          </div>
        </template>

        <!-- Typing -->
        <div v-if="loading" class="animate-fade-in">
          <div class="glass rounded-2xl px-4 py-3 inline-flex items-center gap-2">
            <span class="text-xs text-text-dim">Analisando</span>
            <span v-for="d in 3" :key="d" class="w-1.5 h-1.5 rounded-full bg-primary" :style="{ animation: `pulse-dot 1.4s ease-in-out ${d * 0.2}s infinite` }"></span>
          </div>
        </div>
      </div>

      <!-- Input -->
      <div class="border-t border-white/5 px-4 py-3">
        <div class="max-w-4xl mx-auto flex items-center gap-2">
          <input v-model="currentQuery" @keydown.enter.prevent="ask(currentQuery); currentQuery = ''" placeholder="Digite sua pergunta..." class="input-cyber flex-1" :disabled="loading">
          <button @click="ask(currentQuery); currentQuery = ''" :disabled="loading || !currentQuery?.trim()" class="btn-primary flex items-center gap-2 px-5">
            <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
            Enviar
          </button>
        </div>
      </div>
    </main>
  </div>
</template>

<script>
export default { data() { return { currentQuery: '' } } }
</script>
