<template>
  <div class="ai-layout">
    <!-- 左侧：AI 对话面板（SSE 逐字渲染） -->
    <el-card class="chat-card" shadow="never">
      <template #header>AI 运营助手（DeepSeek 流式）</template>
      <div class="messages" ref="messagesRef">
        <div v-for="(m, i) in messages" :key="i" :class="['msg', m.role]">
          <div class="bubble">{{ m.text }}<span v-if="m.streaming" class="cursor">▍</span></div>
        </div>
      </div>
      <div class="input-bar">
        <el-input
          v-model="input"
          placeholder="例如：MOCK-002 库存不足怎么办？"
          :disabled="streaming"
          @keyup.enter="onSend"
        />
        <el-button type="primary" :loading="streaming" @click="onSend">发送</el-button>
      </div>
    </el-card>

    <!-- 右侧：AI 建议卡片流 -->
    <el-card class="suggestion-card" shadow="never">
      <template #header>
        <div class="sug-header">
          <span>AI 建议（{{ suggestions.length }}）</span>
          <el-button size="small" type="primary" @click="genVisible = true">生成建议</el-button>
        </div>
      </template>
      <el-empty v-if="!suggestions.length" description="暂无建议，点击右上角生成" />
      <div v-for="s in suggestions" :key="s.id" class="sug-item">
        <div class="sug-title">
          <el-tag size="small" :type="s.type === 'restock' ? 'warning' : 'primary'">
            {{ s.type === 'restock' ? '补货' : '定价' }}
          </el-tag>
          <!-- 来源徽标：规则引擎兜底建议无 source 字段 -->
          <el-tag size="small" :type="s.source === 'ai' ? 'success' : 'info'" effect="plain">
            {{ s.source === 'ai' ? 'DeepSeek' : '规则引擎' }}
          </el-tag>
          <span class="sug-time">{{ s.created_at?.slice(5, 16).replace('T', ' ') }}</span>
        </div>
        <!-- 按 type 渲染建议内容 -->
        <template v-if="s.type === 'restock'">
          <p>建议补货 <b>{{ s.content.quantity }}</b> 件（优先级：{{ s.content.priority }}）</p>
        </template>
        <template v-else>
          <p>建议售价 <b>￥{{ s.content.suggested_price }}</b>（区间 {{ s.content.price_range?.[0] }} ~ {{ s.content.price_range?.[1] }}）</p>
        </template>
        <p class="sug-reason">{{ s.content.reason || s.content.strategy }}</p>
        <p class="sug-refs" v-if="s.rule_refs?.length">引用规则：{{ s.rule_refs.length }} 条</p>
      </div>
    </el-card>

    <!-- 生成建议 dialog：选商品 + 类型 -->
    <el-dialog v-model="genVisible" title="生成 AI 建议" width="420px">
      <el-form label-width="80px">
        <el-form-item label="商品">
          <el-select v-model="genForm.product_id" filterable style="width: 100%">
            <el-option v-for="p in products" :key="p.id" :label="`${p.sku} ${p.name}`" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="genForm.type">
            <el-radio-button value="restock">补货建议</el-radio-button>
            <el-radio-button value="pricing">定价建议</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="genVisible = false">取消</el-button>
        <el-button type="primary" :loading="generating" @click="onGenerate">生成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { aiApi, productsApi } from '@/api'
import type { AiSuggestion, Product } from '@/types'

// ---------- 对话（SSE 流式） ----------
interface ChatMessage {
  role: 'user' | 'ai'
  text: string
  streaming?: boolean
}

const messages = ref<ChatMessage[]>([
  { role: 'ai', text: '你好！我是 AI 运营助手，可以询问库存、补货、定价问题。' },
])
const input = ref('')
const streaming = ref(false)
const messagesRef = ref<HTMLElement | null>(null)

// nextTick 返回 Promise，签名与其保持一致
const scrollBottom = (): Promise<void> =>
  nextTick(() => {
    if (messagesRef.value) messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  })

/**
 * 发送消息：fetch + ReadableStream 解析 SSE（EventSource 不支持 POST）。
 * 帧格式 data: {"delta": "..."}，结束帧 data: [DONE]。
 */
async function onSend(): Promise<void> {
  const text = input.value.trim()
  if (!text || streaming.value) return
  input.value = ''
  streaming.value = true

  // 用户消息 + 占位的 AI 消息（streaming=true 显示光标动画）
  messages.value.push({ role: 'user', text })
  const aiMsg = reactive<ChatMessage>({ role: 'ai', text: '', streaming: true })
  messages.value.push(aiMsg)
  scrollBottom()

  try {
    const { useAuthStore } = await import('@/stores/auth')
    const authStore = useAuthStore()
    const resp = await fetch('/api/ai/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authStore.token}`,
      },
      body: JSON.stringify({ message: text }),
    })
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)

    // 逐块读取并按 SSE 帧边界（\n\n）切分
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() as string // 最后一段可能不完整，留到下一轮
      for (const part of parts) {
        if (!part.startsWith('data: ')) continue
        const payload = part.slice(6)
        if (payload === '[DONE]') continue
        const { delta } = JSON.parse(payload) as { delta: string }
        aiMsg.text += delta // 逐字追加，实现"打字机"效果
        scrollBottom()
      }
    }
  } catch (e) {
    aiMsg.text += `\n[请求失败：${(e as Error).message}]`
  } finally {
    aiMsg.streaming = false
    streaming.value = false
    scrollBottom()
  }
}

// ---------- 建议卡片流 ----------
// 后端列表返回的是"内容 + 来源"扁平结构，与 AiSuggestion 略有差异，这里定义展示类型
interface SuggestionView {
  id: string
  type: 'restock' | 'pricing' | 'alert'
  content: { quantity?: number; priority?: string; reason?: string; suggested_price?: number; price_range?: number[]; strategy?: string }
  rule_refs: string[]
  source?: 'ai' | 'rule'
  created_at: string
}

const suggestions = ref<SuggestionView[]>([])
const products = ref<Product[]>([])
const genVisible = ref(false)
const generating = ref(false)
const genForm = reactive<{ product_id: string; type: 'restock' | 'pricing' }>({
  product_id: '',
  type: 'restock',
})

async function loadSuggestions(): Promise<void> {
  const data = await aiApi.listSuggestions({ page: 1, page_size: 20 })
  suggestions.value = data.items as unknown as SuggestionView[]
}

async function onGenerate(): Promise<void> {
  generating.value = true
  try {
    await aiApi.advice({ product_id: genForm.product_id, type: genForm.type })
    ElMessage.success('建议已生成')
    genVisible.value = false
    loadSuggestions()
  } finally {
    generating.value = false
  }
}

// onMounted 回调需返回 void，异步逻辑收敛到 async 函数内
onMounted(() => {
  loadSuggestions()
  void (async () => {
    const data = await productsApi.list({ page: 1, page_size: 100 })
    products.value = data.items
    if (data.items.length) genForm.product_id = data.items[0].id
  })()
})
</script>

<style scoped>
.ai-layout { display: flex; gap: 12px; height: calc(100vh - 120px); }
.chat-card { flex: 1; display: flex; flex-direction: column; }
.chat-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.messages { flex: 1; overflow-y: auto; padding: 8px; }
.msg { display: flex; margin-bottom: 10px; }
.msg.user { justify-content: flex-end; }
.bubble {
  max-width: 75%;
  padding: 8px 12px;
  border-radius: 8px;
  white-space: pre-wrap;
  background: #f4f4f5;
}
.msg.user .bubble { background: var(--s-primary); color: #fff; }
.cursor { animation: blink 1s infinite; }
@keyframes blink { 50% { opacity: 0; } }
.input-bar { display: flex; gap: 8px; padding-top: 8px; }
.suggestion-card { width: 380px; overflow-y: auto; }
.sug-header { display: flex; justify-content: space-between; align-items: center; }
.sug-item { border: 1px solid #ebeef5; border-radius: 6px; padding: 10px; margin-bottom: 10px; }
.sug-title { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; }
.sug-time { margin-left: auto; color: #909399; font-size: 12px; }
.sug-reason { color: #606266; font-size: 13px; margin-top: 4px; }
.sug-refs { color: #909399; font-size: 12px; }
</style>
