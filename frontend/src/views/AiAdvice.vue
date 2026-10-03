<template>
  <div class="ai-layout">
    <!-- 最左：会话列表（方案 B：历史后端持久化，刷新/换设备可恢复） -->
    <el-card class="conv-card" shadow="never">
      <template #header>
        <div class="conv-header">
          <span>会话</span>
          <el-button size="small" :disabled="streaming" @click="newChat">新对话</el-button>
        </div>
      </template>
      <el-empty v-if="!conversations.length" description="暂无会话" :image-size="60" />
      <div
        v-for="c in conversations"
        :key="c.id"
        :class="['conv-item', { active: c.id === currentConvId }]"
        @click="selectConversation(c.id)"
      >
        <span class="conv-title" :title="c.title">{{ c.title }}</span>
        <el-icon class="conv-del" title="删除会话" @click.stop="onDeleteConversation(c.id)"><Delete /></el-icon>
      </div>
    </el-card>

    <!-- 左侧：AI 对话面板（SSE 逐字渲染） -->
    <el-card class="chat-card" shadow="never">
      <template #header>AI 运营助手（DeepSeek 流式）</template>
      <div class="messages" ref="messagesRef">
        <div v-for="(m, i) in messages" :key="i" :class="['msg', m.role]">
          <!-- AI 气泡走 Markdown 渲染（utils/markdown，html:false 防 XSS）；
               用户气泡保持纯文本插值；流式光标在 v-html 节点之外避免被覆盖 -->
          <div v-if="m.role === 'ai'" class="bubble">
            <span class="md-body" v-html="renderMarkdown(m.text)"></span>
            <span v-if="m.streaming" class="cursor">▍</span>
          </div>
          <div v-else class="bubble">{{ m.text }}</div>
        </div>
      </div>
      <div class="input-bar">
        <el-input
          v-model="input"
          placeholder="例如：MOCK-002 库存不足怎么办？"
          :disabled="streaming"
          autocomplete="off"
          @keyup.enter="onSend"
        />
        <el-button type="primary" :loading="streaming" @click="onSend">发送</el-button>
      </div>
    </el-card>

    <!-- 右侧：Agent 工作流 + AI 建议卡片流 -->
    <el-card class="suggestion-card" shadow="never">
      <template #header>
        <div class="sug-header">
          <span>Agent 工作流</span>
          <el-button size="small" type="warning" :loading="agentRunning" :disabled="streaming" @click="onRunAgent">
            生成补货采购计划
          </el-button>
        </div>
      </template>
      <!-- Agent 步骤时间线：SSE 逐步点亮（scan→calc→group→po→done） -->
      <el-timeline v-if="agentSteps.length" style="padding-left: 4px">
        <el-timeline-item
          v-for="(s, i) in agentSteps" :key="i"
          :type="i === agentSteps.length - 1 && !agentRunning ? 'success' : 'primary'"
          :timestamp="s.step"
        >
          {{ s.detail }}
        </el-timeline-item>
      </el-timeline>
      <div v-if="agentPoLink" class="agent-po-link">
        采购单 <b>{{ agentPoLink.po_no }}</b> 已生成，
        <router-link to="/procurement">去采购管理处理 →</router-link>
      </div>
      <el-divider style="margin: 14px 0" />
      <div class="sug-header" style="margin-bottom: 10px">
        <span>AI 建议（{{ suggestions.length }}）</span>
        <div style="display: flex; gap: 6px">
          <el-button size="small" @click="kbVisible = true">知识库</el-button>
          <el-button size="small" type="primary" @click="genVisible = true">生成建议</el-button>
        </div>
      </div>
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
          <!-- quantity=0 无行动价值 → 转译为"库存充足"提示，
               避免"建议补货 0 件 + low/none"的歧义展示 -->
          <p v-if="!s.content.quantity">库存充足，暂无需补货</p>
          <p v-else>建议补货 <b>{{ s.content.quantity }}</b> 件（优先级：{{ s.content.priority }}）</p>
        </template>
        <template v-else>
          <p>建议售价 <b>￥{{ s.content.suggested_price }}</b>（区间 {{ s.content.price_range?.[0] }} ~ {{ s.content.price_range?.[1] }}）</p>
        </template>
        <p class="sug-reason">{{ s.content.reason || s.content.strategy }}</p>
        <!-- 优先展示规则标题（UUID 对运营者无可读性），旧数据降级为条数 -->
        <p class="sug-refs" v-if="s.rule_titles?.length">引用规则：{{ s.rule_titles.join('、') }}</p>
        <p class="sug-refs" v-else-if="s.rule_refs?.length">引用规则：{{ s.rule_refs.length }} 条</p>
        <!-- 补货建议一键转采购单（ERP 业务闭环入口） -->
        <el-button
          v-if="s.type === 'restock' && s.content.quantity && canWrite"
          size="small" type="warning" plain style="margin-top: 8px"
          :loading="convertingId === s.id"
          @click="onSuggestToPo(s)"
        >转采购单</el-button>
      </div>
    </el-card>

    <!-- 知识库管理弹窗：RAG 规则 CRUD -->
    <el-dialog v-model="kbVisible" title="运营规则知识库（RAG 数据源）" width="640px">
      <div style="display: flex; gap: 8px; margin-bottom: 12px">
        <el-input v-model="kbForm.title" placeholder="规则标题" style="width: 200px" size="small" />
        <el-input v-model="kbForm.content" placeholder="规则内容" style="flex: 1" size="small" />
        <el-button type="primary" size="small" @click="onSaveRule">保存</el-button>
      </div>
      <el-table :data="rules" size="small" max-height="320">
        <el-table-column prop="title" label="标题" width="180" />
        <el-table-column prop="content" label="内容" min-width="240" show-overflow-tooltip />
        <el-table-column label="操作" width="120" align="center">
          <template #default="{ row }">
            <el-button size="small" @click="onEditRule(row)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="onDeleteRule(row)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p class="hint">规则变更立即生效于 RAG 检索（AI 建议/对话即时引用新规则）。</p>
    </el-dialog>

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
import { ref, reactive, computed, onMounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { aiApi, agentApi, productsApi, procurementApi } from '@/api'
import { renderMarkdown } from '@/utils/markdown'
import { useAuthStore } from '@/stores/auth'
import type { AiSuggestion, ChatMessageOut, Conversation, Product, Supplier } from '@/types'

const auth = useAuthStore()

// ---------- 对话（SSE 流式） ----------
interface ChatMessage {
  role: 'user' | 'ai'
  text: string
  streaming?: boolean
}

const router = useRouter()
const canWrite = computed(() => ['admin', 'operator'].includes(auth?.role ?? 'viewer'))

const WELCOME = '你好！我是 AI 运营助手，可以询问库存、补货、定价问题。'
const messages = ref<ChatMessage[]>([{ role: 'ai', text: WELCOME }])
const input = ref('')
const streaming = ref(false)
const messagesRef = ref<HTMLElement | null>(null)

// ---------- 会话（方案 B：历史持久化在后端，刷新可恢复） ----------
const conversations = ref<Conversation[]>([])
const currentConvId = ref('')

/** 拉取会话列表；selectFirst=true 时自动恢复最近会话（刷新后回填） */
async function loadConversations(selectFirst = false): Promise<void> {
  const data = await aiApi.conversations()
  conversations.value = data.items
  // 刷新进入页面：默认恢复最近一次会话
  if (selectFirst && !currentConvId.value && data.items.length) {
    await selectConversation(data.items[0].id)
  }
  // 当前会话已被删除（可能在其他端）→ 重置为欢迎语
  if (currentConvId.value && !data.items.some((c) => c.id === currentConvId.value)) {
    resetToWelcome()
  }
}

/** 切换会话：拉取消息明细，映射为界面气泡（assistant→ai，历史直接完整展示） */
async function selectConversation(id: string): Promise<void> {
  if (id === currentConvId.value || streaming.value) return
  const data = await aiApi.messages(id)
  currentConvId.value = id
  messages.value = data.items.map(
    (m: ChatMessageOut): ChatMessage => ({ role: m.role === 'user' ? 'user' : 'ai', text: m.content })
  )
  scrollBottom()
}

/** 重置为新对话（清空当前会话指针与气泡，仅保留欢迎语） */
function resetToWelcome(): void {
  currentConvId.value = ''
  messages.value = [{ role: 'ai', text: WELCOME }]
}

function newChat(): void {
  if (streaming.value) return
  resetToWelcome()
}

/** 删除会话：确认后调删除接口；删的是当前会话则重置界面 */
async function onDeleteConversation(id: string): Promise<void> {
  try {
    await ElMessageBox.confirm('删除后该会话历史无法恢复，确认删除？', '删除会话', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return // 用户取消
  }
  await aiApi.removeConversation(id)
  if (id === currentConvId.value) resetToWelcome()
  loadConversations()
  ElMessage.success('会话已删除')
}

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
    // 会话 ID：空则后端新建（标题取本条消息），否则追加到当前会话；
    // 多轮上下文由后端从会话表加载，前端不再回传 history
    const resp = await fetch('/api/ai/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authStore.token}`,
      },
      body: JSON.stringify({ message: text, conversation_id: currentConvId.value || undefined }),
    })
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)
    // 会话 ID 经响应头返回（流式响应没有 JSON body 可携带）
    const convId = resp.headers.get('X-Conversation-Id')
    if (convId) currentConvId.value = convId

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
    // 刷新会话列表（新会话标题/排序更新）
    loadConversations()
  }
}

// ---------- 建议卡片流 ----------
// 后端列表返回的是"内容 + 来源"扁平结构，与 AiSuggestion 略有差异，这里定义展示类型
interface SuggestionView {
  id: string
  type: 'restock' | 'pricing' | 'alert'
  content: { quantity?: number; priority?: string; reason?: string; suggested_price?: number; price_range?: number[]; strategy?: string }
  rule_refs: string[]
  /** 规则标题（新建议有；旧数据无 → 展示降级为条数） */
  rule_titles?: string[]
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

// ---------- Agent 工作流（SSE 步骤时间线） ----------
interface AgentStep {
  step: string
  detail: string
}
const agentSteps = ref<AgentStep[]>([])
const agentRunning = ref(false)
const agentPoLink = ref<{ po_id: string; po_no: string } | null>(null)

/** 运行 Agent 补货计划：fetch+ReadableStream 解析 step 帧（复用 chat 的 SSE 解析思路） */
async function onRunAgent(): Promise<void> {
  if (agentRunning.value || streaming.value) return
  agentRunning.value = true
  agentSteps.value = []
  agentPoLink.value = null
  try {
    const { useAuthStore } = await import('@/stores/auth')
    const authStore = useAuthStore()
    const resp = await fetch('/api/ai/agent/restock-plan', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authStore.token}`,
      },
      body: JSON.stringify({}),
    })
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`)

    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() as string
      for (const part of parts) {
        if (!part.startsWith('data: ') || part.includes('[DONE]')) continue
        const payload = JSON.parse(part.slice(6))
        if (payload.step) agentSteps.value.push({ step: payload.step, detail: payload.detail })
        if (payload.delta) agentPoLink.value = JSON.parse(payload.delta)
      }
    }
    ElMessage.success('Agent 工作流执行完成')
  } catch (e) {
    ElMessage.error(`Agent 执行失败：${(e as Error).message}`)
  } finally {
    agentRunning.value = false
  }
}

// ---------- 建议转采购单（ERP 业务闭环入口） ----------
const convertingId = ref<string | null>(null)

async function onSuggestToPo(s: SuggestionView): Promise<void> {
  const active = suppliersForPo.value[0]
  if (!active) {
    ElMessage.warning('请先到采购管理页创建供应商')
    return
  }
  convertingId.value = s.id
  try {
    const po = await agentApi.suggestionToPo(s.id, active.id)
    ElMessage.success(`采购单 ${po.po_no} 已生成（草稿），请到采购管理页提交`)
    router.push('/procurement')
  } finally {
    convertingId.value = null
  }
}

const suppliersForPo = ref<Supplier[]>([])

// ---------- 知识库管理（RAG 数据源 CRUD） ----------
const kbVisible = ref(false)
const rules = ref<{ id: string; title: string; content: string }[]>([])
const kbForm = reactive({ title: '', content: '' })
const editingRuleId = ref<string | null>(null)

async function loadRules(): Promise<void> {
  const data = await agentApi.listRules()
  rules.value = data.items
}

function onEditRule(row: { id: string; title: string; content: string }): void {
  editingRuleId.value = row.id
  kbForm.title = row.title
  kbForm.content = row.content
}

async function onSaveRule(): Promise<void> {
  if (!kbForm.title.trim() || !kbForm.content.trim()) {
    ElMessage.warning('标题与内容均不能为空')
    return
  }
  if (editingRuleId.value) {
    await agentApi.updateRule(editingRuleId.value, { ...kbForm })
    ElMessage.success('规则已更新（RAG 检索即时生效）')
  } else {
    await agentApi.createRule({ ...kbForm })
    ElMessage.success('规则已新增')
  }
  editingRuleId.value = null
  kbForm.title = ''
  kbForm.content = ''
  loadRules()
}

async function onDeleteRule(row: { id: string; title: string }): Promise<void> {
  await agentApi.deleteRule(row.id)
  ElMessage.success('规则已删除')
  loadRules()
}

watch(kbVisible, (v) => {
  if (v) loadRules()
})

// onMounted 回调需返回 void，异步逻辑收敛到 async 函数内
onMounted(() => {
  loadSuggestions()
  loadConversations(true) // selectFirst：刷新后自动恢复最近会话
  void (async () => {
    const data = await productsApi.list({ page: 1, page_size: 100 })
    products.value = data.items
    if (data.items.length) genForm.product_id = data.items[0].id
  })()
  void (async () => {
    // 转采购单需要供应商：取第一个启用供应商（多供应商分组为 P1）
    const sup = await procurementApi.listSuppliers()
    suppliersForPo.value = sup.items.filter((s) => s.status === 'active')
  })()
})
</script>

<style scoped>
.ai-layout { display: flex; gap: 12px; height: calc(100vh - 120px); }
/* 会话侧栏：窄栏列表，标题单行省略，激活态高亮 */
.conv-card { width: 210px; display: flex; flex-direction: column; overflow-y: auto; }
.conv-header { display: flex; justify-content: space-between; align-items: center; }
.conv-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
  color: #303133;
}
.conv-item:hover { background: #f5f7fa; }
.conv-item.active { background: var(--s-primary); color: #fff; }
.conv-title { flex: 1; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.conv-del { flex-shrink: 0; opacity: 0; color: inherit; }
.conv-item:hover .conv-del { opacity: 0.7; }
.conv-del:hover { opacity: 1 !important; color: var(--s-danger, #f56c6c); }
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
/* AI 气泡为 Markdown 渲染（块级元素自带间距），关闭整体 pre-wrap 防双重换行 */
.msg.ai .bubble { white-space: normal; }
/* v-html 内容无 scoped 属性，需 :deep 穿透设置排版样式 */
.msg.ai .bubble :deep(.md-body) { line-height: 1.6; font-size: 14px; }
.msg.ai .bubble :deep(p) { margin: 0 0 6px; }
.msg.ai .bubble :deep(p:last-child) { margin-bottom: 0; }
.msg.ai .bubble :deep(ul),
.msg.ai .bubble :deep(ol) { margin: 4px 0 6px; padding-left: 20px; }
.msg.ai .bubble :deep(li) { margin: 2px 0; }
.msg.ai .bubble :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 13px;
}
.msg.ai .bubble :deep(pre) {
  background: rgba(0, 0, 0, 0.06);
  padding: 8px 10px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 6px 0;
}
.msg.ai .bubble :deep(pre code) { background: transparent; padding: 0; }
.msg.ai .bubble :deep(table) { border-collapse: collapse; margin: 6px 0; }
.msg.ai .bubble :deep(th),
.msg.ai .bubble :deep(td) { border: 1px solid #dcdfe6; padding: 4px 8px; font-size: 13px; }
.msg.ai .bubble :deep(a) { color: var(--s-primary); }
.msg.ai .bubble :deep(h1),
.msg.ai .bubble :deep(h2),
.msg.ai .bubble :deep(h3),
.msg.ai .bubble :deep(h4) { margin: 8px 0 6px; font-size: 15px; }
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
