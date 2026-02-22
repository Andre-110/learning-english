<template>
  <div class="control-panel">
    <!-- 用户信息 -->
    <div class="card user-card">
      <div class="user-header">
        <div class="user-avatar">👤</div>
        <div class="user-info">
          <span class="username">{{ auth.username }}</span>
          <span class="user-level badge" :class="levelClass">{{ conversation.cefrLevel }}</span>
        </div>
        <button class="btn btn-ghost btn-sm" @click="auth.logout">退出</button>
      </div>
    </div>

    <!-- AI 服务选择 -->
    <div class="card">
      <div class="card-body">
        <label class="section-label">AI 服务</label>
        <select 
          v-model="selectedService" 
          class="input select"
          @change="handleServiceChange"
        >
          <option value="dashscope">🚀 阿里云 DashScope (流式输出)</option>
          <option value="openrouter">🌐 OpenRouter GPT-4o</option>
        </select>
        <p class="help-text">
          {{ serviceHelpText }}
        </p>
      </div>
    </div>

    <!-- 历史对话列表 -->
    <div class="card">
      <div class="card-header">
        <h3>📚 对话记录</h3>
        <button class="btn btn-ghost btn-sm" @click="loadHistoryList" :disabled="loadingHistory">
          {{ loadingHistory ? '加载中...' : '刷新' }}
        </button>
      </div>
      <div class="card-body history-body">
        <div v-if="historyList.length === 0" class="empty-history">
          暂无历史对话
        </div>
        <div v-else class="history-list">
          <div 
            v-for="item in historyList" 
            :key="item.id" 
            class="history-item"
            :class="{ active: item.id === conversation.conversationId }"
            @click="loadConversation(item.id)"
          >
            <div class="history-title">
              {{ item.title || '对话 ' + item.id.slice(0, 8) }}
            </div>
            <div class="history-meta">
              <span class="history-time">{{ formatDate(item.created_at) }}</span>
              <span class="history-level badge" :class="getLevelClass(item.cefr_level)">
                {{ item.cefr_level || 'A1' }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 累计统计 -->
    <div class="card" v-if="conversation.latestAssessment">
      <div class="card-header">
        <h3>📊 本次评估</h3>
      </div>
      <div class="card-body">
        <div class="assessment-grid">
          <div class="assessment-item">
            <span class="assessment-label">分数</span>
            <span class="assessment-value score">
              {{ conversation.latestAssessment.overall_score || 0 }}
            </span>
          </div>
          <div class="assessment-item">
            <span class="assessment-label">等级</span>
            <span class="assessment-value badge" :class="levelClass">
              {{ conversation.latestAssessment.cefr_level || 'N/A' }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 延迟信息 -->
    <div class="card" v-if="conversation.latency">
      <div class="card-header">
        <h3>⚡ 性能</h3>
      </div>
      <div class="card-body">
        <div class="latency-grid">
          <div class="latency-item">
            <span class="latency-label">LLM</span>
            <span class="latency-value">{{ formatLatency(conversation.latency.llm) }}</span>
          </div>
          <div class="latency-item">
            <span class="latency-label">TTS</span>
            <span class="latency-value">{{ formatLatency(conversation.latency.tts) }}</span>
          </div>
          <div class="latency-item total">
            <span class="latency-label">总计</span>
            <span class="latency-value">{{ formatLatency(conversation.latency.total) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import { useConversationStore } from '../stores/conversation'

const auth = useAuthStore()
const conversation = useConversationStore()

// AI 服务选择
const selectedService = ref('dashscope')

// 历史对话
const historyList = ref([])
const loadingHistory = ref(false)

// 服务帮助文本
const serviceHelpText = computed(() => {
  if (selectedService.value === 'dashscope') {
    return '阿里云 qwen-audio，支持真正的流式输出'
  }
  return 'OpenRouter GPT-4o Audio，延迟约5秒'
})

// 计算属性
const levelClass = computed(() => {
  const level = conversation.cefrLevel?.toUpperCase()
  if (level === 'C2') return 'badge-c2'
  if (level === 'C1') return 'badge-c1'
  if (level === 'B2') return 'badge-b2'
  if (level === 'B1') return 'badge-b1'
  if (level === 'A2') return 'badge-a2'
  return 'badge-a1'
})

// 获取等级样式
function getLevelClass(level) {
  if (!level) return 'badge-a1'
  const upperLevel = level.toUpperCase()
  if (upperLevel === 'C2') return 'badge-c2'
  if (upperLevel === 'C1') return 'badge-c1'
  if (upperLevel === 'B2') return 'badge-b2'
  if (upperLevel === 'B1') return 'badge-b1'
  if (upperLevel === 'A2') return 'badge-a2'
  return 'badge-a1'
}

// 加载历史对话列表
async function loadHistoryList() {
  loadingHistory.value = true
  try {
    const API_BASE = import.meta.env.PROD ? '/english' : ''
    const response = await fetch(`${API_BASE}/conversations/list?user_id=${auth.userId}`, {
      headers: auth.getAuthHeaders()
    })
    if (response.ok) {
      const data = await response.json()
      historyList.value = data.conversations || []
    }
  } catch (e) {
    console.error('加载历史对话失败:', e)
  } finally {
    loadingHistory.value = false
  }
}

// 加载指定对话
async function loadConversation(conversationId) {
  // TODO: 实现加载历史对话的逻辑
  console.log('加载对话:', conversationId)
}

function handleModeChange() {
  // 如果已连接，提示需要重新开始对话
  if (conversation.isConnected) {
    conversation.disconnect()
  }
}

// 切换 AI 服务
async function handleServiceChange() {
  // 保存到后端
  try {
    const API_BASE = import.meta.env.PROD ? '/english' : ''
    await fetch(`${API_BASE}/settings/llm-service`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...auth.getAuthHeaders()
      },
      body: JSON.stringify({ service: selectedService.value })
    })
    
    // 如果已连接，断开重连
    if (conversation.isConnected) {
      conversation.disconnect()
    }
  } catch (e) {
    console.error('切换服务失败:', e)
  }
}

// 加载当前服务设置
async function loadCurrentService() {
  try {
    const API_BASE = import.meta.env.PROD ? '/english' : ''
    const response = await fetch(`${API_BASE}/settings/llm-service`, {
      headers: auth.getAuthHeaders()
    })
    if (response.ok) {
      const data = await response.json()
      selectedService.value = data.service || 'dashscope'
    }
  } catch (e) {
    console.error('加载服务设置失败:', e)
  }
}

function formatLatency(value) {
  if (typeof value !== 'number') return 'N/A'
  return `${value.toFixed(2)}s`
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const diffDays = Math.floor((now - d) / (1000 * 60 * 60 * 24))
  
  if (diffDays === 0) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  } else if (diffDays === 1) {
    return '昨天'
  } else if (diffDays < 7) {
    return `${diffDays}天前`
  } else {
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  }
}

// 初始化
onMounted(() => {
  loadHistoryList()
  loadCurrentService()
})
</script>

<style scoped>
.control-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.user-card {
  padding: 16px;
}

.user-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--primary-light), var(--primary));
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.3rem;
}

.user-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.username {
  font-weight: 600;
  color: var(--text-primary);
}

.user-level {
  width: fit-content;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 0.85rem;
}

.section-label {
  display: block;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.select {
  cursor: pointer;
}

.help-text {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin-top: 8px;
  margin-bottom: 0;
}

/* 评估结果 */
.card-header h3 {
  font-size: 0.95rem;
  margin: 0;
}

.assessment-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.assessment-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.assessment-label {
  font-size: 0.8rem;
  color: var(--text-muted);
}

.assessment-value {
  font-size: 1.5rem;
  font-weight: 700;
}

.assessment-value.score {
  color: var(--primary);
}

.assessment-value.badge {
  font-size: 1.2rem;
}

/* 表达亮点 */
.good-expressions {
  margin-bottom: 16px;
}

.good-expressions h4 {
  font-size: 0.85rem;
  margin: 0 0 8px 0;
  color: var(--success);
}

.expression-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.expression-tag {
  padding: 4px 10px;
  background: rgba(72, 187, 120, 0.15);
  color: var(--success);
  border-radius: var(--radius-full);
  font-size: 0.8rem;
  font-weight: 500;
}

/* 纠错建议 */
.corrections {
  margin-bottom: 16px;
}

.corrections h4 {
  font-size: 0.85rem;
  margin: 0 0 10px 0;
  color: var(--primary);
}

.correction-item {
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  margin-bottom: 8px;
  border-left: 3px solid var(--primary);
}

.correction-original,
.correction-corrected {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 6px;
}

.correction-original .label,
.correction-corrected .label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-muted);
  min-width: 40px;
}

.correction-original .text {
  color: var(--text-secondary);
}

.strikethrough {
  text-decoration: line-through;
  opacity: 0.7;
}

.correction-corrected .text {
  color: var(--success);
  font-weight: 500;
}

.highlight {
  background: rgba(72, 187, 120, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
}

.correction-explanation {
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-top: 4px;
  padding-top: 8px;
  border-top: 1px dashed var(--border);
}

/* 改进建议 */
.suggestions {
  margin-bottom: 16px;
}

.suggestions h4 {
  font-size: 0.85rem;
  margin: 0 0 8px 0;
  color: var(--info);
}

.suggestions ul {
  margin: 0;
  padding-left: 20px;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.suggestions li {
  margin-bottom: 4px;
}

.strengths, .weaknesses {
  margin-top: 12px;
}

.strengths h4, .weaknesses h4 {
  font-size: 0.85rem;
  margin: 0 0 8px 0;
}

.strengths h4 {
  color: var(--success);
}

.weaknesses h4 {
  color: var(--warning);
}

.strengths ul, .weaknesses ul {
  margin: 0;
  padding-left: 20px;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.strengths li, .weaknesses li {
  margin-bottom: 4px;
}

/* 延迟信息 */
.latency-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.latency-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
}

.latency-item.total {
  grid-column: span 2;
  background: linear-gradient(135deg, var(--primary-light), var(--primary));
  color: white;
}

.latency-label {
  font-size: 0.8rem;
  opacity: 0.8;
}

.latency-value {
  font-weight: 600;
}

/* 历史对话列表 */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.history-body {
  max-height: 240px;
  overflow-y: auto;
  padding: 0 !important;
}

.empty-history {
  padding: 24px;
  text-align: center;
  color: var(--text-muted);
  font-size: 0.9rem;
}

.history-list {
  display: flex;
  flex-direction: column;
}

.history-item {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-light);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.history-item:last-child {
  border-bottom: none;
}

.history-item:hover {
  background: var(--bg-tertiary);
}

.history-item.active {
  background: linear-gradient(135deg, rgba(78, 205, 196, 0.1), rgba(78, 205, 196, 0.05));
  border-left: 3px solid var(--secondary);
}

.history-title {
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.history-time {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.history-level {
  font-size: 0.7rem;
  padding: 2px 6px;
}

/* 6 种 CEFR 等级颜色 */
.badge-a1 {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.badge-a2 {
  background: rgba(246, 173, 85, 0.15);
  color: #f6ad55;
}

.badge-b1 {
  background: rgba(99, 179, 237, 0.15);
  color: #63b3ed;
}

.badge-b2 {
  background: rgba(56, 189, 248, 0.15);
  color: #38bdf8;
}

.badge-c1 {
  background: rgba(72, 187, 120, 0.15);
  color: #48bb78;
}

.badge-c2 {
  background: rgba(168, 85, 247, 0.15);
  color: #a855f7;
}
</style>

