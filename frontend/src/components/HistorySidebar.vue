<template>
  <aside class="history-sidebar" :class="{ collapsed: isCollapsed }">
    <!-- 折叠按钮 -->
    <button class="collapse-btn" @click="toggleCollapse">
      <span class="collapse-icon">{{ isCollapsed ? '→' : '←' }}</span>
    </button>

    <!-- 侧边栏内容 -->
    <div class="sidebar-content" v-show="!isCollapsed">
      <!-- 功能导航 - 每日发现功能暂时隐藏 -->
      <!-- 
      <div class="nav-tabs">
        <button 
          class="nav-tab" 
          :class="{ active: activeView === 'conversation' }"
          @click="switchView('conversation')"
        >
          <span class="nav-icon">💬</span>
          <span class="nav-text">对话练习</span>
        </button>
        <button 
          class="nav-tab" 
          :class="{ active: activeView === 'discovery' }"
          @click="switchView('discovery')"
        >
          <span class="nav-icon">🌟</span>
          <span class="nav-text">每日发现</span>
        </button>
      </div>
      -->

      <!-- 对话练习模式的内容 -->
      <template v-if="activeView === 'conversation'">
        <!-- 新对话按钮 -->
        <button class="new-chat-btn" @click="startNewConversation" :disabled="isStarting">
          <span class="btn-icon">✨</span>
          <span class="btn-text">{{ isStarting ? '创建中...' : '新对话' }}</span>
        </button>

        <!-- 🆕 模式选择 -->
        <div class="mode-selector">
          <div class="mode-label">对话模式</div>
          <div class="mode-options">
            <button 
              class="mode-option"
              :class="{ active: conversation.isAutoMode }"
              @click="setMode(true)"
              title="自动对话，AI说完后自动开始监听"
            >
              <span class="mode-icon">🤖</span>
              <span class="mode-name">对话</span>
            </button>
            <button 
              class="mode-option"
              :class="{ active: !conversation.isAutoMode }"
              @click="setMode(false)"
              title="手动控制，看完评分后点击开始"
            >
              <span class="mode-icon">📝</span>
              <span class="mode-name">练习</span>
            </button>
          </div>
          <div class="mode-hint">
            {{ conversation.isAutoMode ? '自动对话，流畅交流' : '手动控制，看评分再继续' }}
          </div>
        </div>

        <!-- 搜索框 -->
        <div class="search-box">
          <span class="search-icon">🔍</span>
          <input 
            type="text" 
            v-model="searchQuery" 
            placeholder="搜索对话..."
            class="search-input"
          />
        </div>
      </template>

      <!-- 每日发现模式的内容 - 暂时隐藏 -->
      <!-- 
      <template v-if="activeView === 'discovery'">
        ... 每日发现内容已隐藏 ...
      </template>
      -->

      <!-- 对话列表（仅在对话模式显示） -->
      <div class="history-section" v-if="activeView === 'conversation'">
        <div class="section-header">
          <span class="section-title">历史对话</span>
          <button class="refresh-btn" @click="loadHistory" :disabled="isLoading">
            <span :class="{ spinning: isLoading }">🔄</span>
          </button>
        </div>

        <!-- 加载状态 -->
        <div v-if="isLoading" class="loading-state">
          <div class="loading-spinner"></div>
          <span>加载中...</span>
        </div>

        <!-- 空状态 -->
        <div v-else-if="filteredHistory.length === 0" class="empty-state">
          <div class="empty-icon">💬</div>
          <p v-if="searchQuery">未找到匹配的对话</p>
          <p v-else>还没有对话记录</p>
          <p class="empty-hint">点击上方按钮开始新对话</p>
        </div>

        <!-- 对话列表 -->
        <div v-else class="history-list">
          <!-- 今天 -->
          <div v-if="todayConversations.length > 0" class="history-group">
            <div class="group-label">今天</div>
            <div 
              v-for="item in todayConversations" 
              :key="item.id"
              class="history-item"
              :class="{ active: item.id === currentConversationId }"
              @click="selectConversation(item)"
            >
              <div class="item-icon">💬</div>
              <div class="item-content">
                <div class="item-title">{{ getTitle(item) }}</div>
                <div class="item-meta">
                  <span class="item-time">{{ formatTime(item.created_at) }}</span>
                  <!-- 等级标签 - 暂时隐藏
                  <span class="item-level" :class="getLevelClass(item.cefr_level)">
                    {{ item.cefr_level || 'A1' }}
                  </span>
                  -->
                </div>
              </div>
              <button class="item-menu" @click.stop="showMenu(item, $event)">⋮</button>
            </div>
          </div>

          <!-- 昨天 -->
          <div v-if="yesterdayConversations.length > 0" class="history-group">
            <div class="group-label">昨天</div>
            <div 
              v-for="item in yesterdayConversations" 
              :key="item.id"
              class="history-item"
              :class="{ active: item.id === currentConversationId }"
              @click="selectConversation(item)"
            >
              <div class="item-icon">💬</div>
              <div class="item-content">
                <div class="item-title">{{ getTitle(item) }}</div>
                <div class="item-meta">
                  <span class="item-time">{{ formatTime(item.created_at) }}</span>
                  <!-- 等级标签 - 暂时隐藏
                  <span class="item-level" :class="getLevelClass(item.cefr_level)">
                    {{ item.cefr_level || 'A1' }}
                  </span>
                  -->
                </div>
              </div>
              <button class="item-menu" @click.stop="showMenu(item, $event)">⋮</button>
            </div>
          </div>

          <!-- 更早 -->
          <div v-if="olderConversations.length > 0" class="history-group">
            <div class="group-label">更早</div>
            <div 
              v-for="item in olderConversations" 
              :key="item.id"
              class="history-item"
              :class="{ active: item.id === currentConversationId }"
              @click="selectConversation(item)"
            >
              <div class="item-icon">💬</div>
              <div class="item-content">
                <div class="item-title">{{ getTitle(item) }}</div>
                <div class="item-meta">
                  <span class="item-time">{{ formatDate(item.created_at) }}</span>
                  <!-- 等级标签 - 暂时隐藏
                  <span class="item-level" :class="getLevelClass(item.cefr_level)">
                    {{ item.cefr_level || 'A1' }}
                  </span>
                  -->
                </div>
              </div>
              <button class="item-menu" @click.stop="showMenu(item, $event)">⋮</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部用户信息（仅在对话模式显示完整信息） -->
      <div class="sidebar-footer">
        <div class="user-info">
          <div class="user-avatar">👤</div>
          <div class="user-details">
            <span class="user-name">{{ auth.username }}</span>
            <!-- 用户等级和分数 - 暂时隐藏
            <div class="user-score-row">
              <span class="user-level" :class="getLevelClass(userLevel)">{{ userLevel }}</span>
              <span class="user-score" v-if="userScore">{{ userScore }}分</span>
            </div>
            -->
          </div>
        </div>
        <button class="logout-btn" @click="auth.logout" title="退出登录">
          🚪
        </button>
      </div>
    </div>

    <!-- 折叠状态下的迷你视图 -->
    <div class="mini-sidebar" v-show="isCollapsed">
      <button class="mini-btn" @click="startNewConversation" title="新对话">✨</button>
      <div class="mini-divider"></div>
      <div class="mini-history">
        <div 
          v-for="item in historyList.slice(0, 5)" 
          :key="item.id"
          class="mini-item"
          :class="{ active: item.id === currentConversationId }"
          @click="selectConversation(item)"
          :title="getTitle(item)"
        >
          💬
        </div>
      </div>
      <div class="mini-footer">
        <div class="mini-avatar" @click="toggleCollapse">👤</div>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useAuthStore } from '../stores/auth'
import { useConversationStore } from '../stores/conversation'

const auth = useAuthStore()
const conversation = useConversationStore()

// 定义事件
const emit = defineEmits(['view-change', 'topic-select', 'load-article', 'open-subpage'])

// 状态
const isCollapsed = ref(false)
const isLoading = ref(false)
const isStarting = ref(false)
const searchQuery = ref('')
const historyList = ref([])
const activeView = ref('conversation') // 'conversation' | 'discovery'
const selectedTopic = ref(null)
const customTopicInput = ref('')

// 每日发现相关状态
const isLoadingArticles = ref(false)
const isLoadingVocabulary = ref(false)
const articleHistory = ref([])
const vocabularyList = ref([])

// 话题分类
const topics = ref([
  { id: 'tech', name: '科技前沿', icon: '🚀' },
  { id: 'health', name: '健康生活', icon: '💪' },
  { id: 'culture', name: '文化艺术', icon: '🎨' },
  { id: 'business', name: '商业财经', icon: '📈' },
  { id: 'travel', name: '旅行探索', icon: '✈️' },
  { id: 'food', name: '美食天地', icon: '🍜' },
])

// 计算属性
const currentConversationId = computed(() => conversation.conversationId)
const userLevel = computed(() => conversation.userProfile?.cefr_level || 'A1')
const userScore = computed(() => {
  const score = conversation.userProfile?.overall_score
  return score ? Math.round(score) : null
})

// 过滤后的历史
const filteredHistory = computed(() => {
  if (!searchQuery.value) return historyList.value
  const query = searchQuery.value.toLowerCase()
  return historyList.value.filter(item => {
    const title = getTitle(item).toLowerCase()
    return title.includes(query)
  })
})

// 按时间分组
const todayConversations = computed(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return filteredHistory.value.filter(item => {
    const date = new Date(item.created_at)
    return date >= today
  })
})

const yesterdayConversations = computed(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  return filteredHistory.value.filter(item => {
    const date = new Date(item.created_at)
    return date >= yesterday && date < today
  })
})

const olderConversations = computed(() => {
  const yesterday = new Date()
  yesterday.setHours(0, 0, 0, 0)
  yesterday.setDate(yesterday.getDate() - 1)
  return filteredHistory.value.filter(item => {
    const date = new Date(item.created_at)
    return date < yesterday
  })
})

// 方法
function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
  // 保存状态到 localStorage
  localStorage.setItem('sidebar-collapsed', isCollapsed.value)
}

// 供父组件（如 App 手机端工具栏）调用：打开/关闭侧栏
defineExpose({
  open() {
    isCollapsed.value = false
  },
  close() {
    isCollapsed.value = true
  }
})

async function loadHistory() {
  if (!auth.isLoggedIn) return
  
  isLoading.value = true
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
    isLoading.value = false
  }
}

// 🆕 设置对话模式（对话模式=自动，练习模式=手动）
function setMode(isAutoMode) {
  if (conversation.isAutoMode !== isAutoMode) {
    conversation.toggleAutoMode()
  }
}

async function startNewConversation() {
  isStarting.value = true
  try {
    await conversation.startConversation()
    // 刷新历史列表
    await loadHistory()
  } finally {
    isStarting.value = false
  }
}

async function selectConversation(item) {
  // 加载历史对话
  console.log('加载对话:', item.id)
  
  try {
    const API_BASE = import.meta.env.PROD ? '/english' : ''
    const response = await fetch(`${API_BASE}/conversations/${item.id}/messages`, {
      headers: auth.getAuthHeaders()
    })
    
    if (!response.ok) {
      throw new Error('加载对话失败')
    }
    
    const data = await response.json()
    
    // 调用 conversation store 的方法加载消息
    conversation.loadHistoryConversation(item.id, data.messages, data.title)
    
  } catch (e) {
    console.error('加载历史对话失败:', e)
  }
}

function showMenu(item, event) {
  // TODO: 实现右键菜单（删除、重命名等）
  console.log('显示菜单:', item.id)
}

function getTitle(item) {
  if (item.title) return item.title
  // 从对话内容生成标题
  if (item.first_message) {
    return item.first_message.substring(0, 30) + (item.first_message.length > 30 ? '...' : '')
  }
  return '对话 ' + (item.id?.slice(0, 8) || '')
}

function formatTime(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function getLevelClass(level) {
  if (!level) return 'level-a1'
  const upperLevel = level.toUpperCase()
  if (upperLevel === 'C2') return 'level-c2'
  if (upperLevel === 'C1') return 'level-c1'
  if (upperLevel === 'B2') return 'level-b2'
  if (upperLevel === 'B1') return 'level-b1'
  if (upperLevel === 'A2') return 'level-a2'
  return 'level-a1'
}

function getLevelName(level) {
  if (!level) return 'Beginner'
  const upperLevel = level.toUpperCase()
  const names = {
    'A1': 'Beginner',
    'A2': 'Elementary',
    'B1': 'Intermediate',
    'B2': 'Upper Intermediate',
    'C1': 'Advanced',
    'C2': 'Proficient'
  }
  return names[upperLevel] || 'Beginner'
}

// 切换视图
function switchView(view) {
  activeView.value = view
  emit('view-change', view)
}

// 选择话题
function selectTopic(topicId) {
  selectedTopic.value = topicId
  customTopicInput.value = '' // 清空自定义输入
  emit('topic-select', topicId)
}

// 提交自定义话题
function submitCustomTopic() {
  const topic = customTopicInput.value.trim()
  if (!topic) return
  
  selectedTopic.value = null // 取消预设话题的选中状态
  emit('topic-select', { type: 'custom', topic: topic })
}

// ========== 历史阅读和生词本 ==========

// 加载阅读历史
async function loadArticleHistory() {
  if (!auth.isLoggedIn) return
  
  isLoadingArticles.value = true
  try {
    const API_BASE = import.meta.env.PROD ? '/english' : ''
    const response = await fetch(`${API_BASE}/discovery/articles?user_id=${auth.userId}&limit=10`, {
      headers: auth.getAuthHeaders()
    })
    if (response.ok) {
      const data = await response.json()
      articleHistory.value = data.articles || []
    }
  } catch (e) {
    console.error('加载阅读历史失败:', e)
  } finally {
    isLoadingArticles.value = false
  }
}

// 加载生词本
async function loadVocabulary() {
  if (!auth.isLoggedIn) return
  
  isLoadingVocabulary.value = true
  try {
    const API_BASE = import.meta.env.PROD ? '/english' : ''
    const response = await fetch(`${API_BASE}/discovery/vocabulary?user_id=${auth.userId}&limit=20`, {
      headers: auth.getAuthHeaders()
    })
    if (response.ok) {
      const data = await response.json()
      vocabularyList.value = data.vocabulary || []
    }
  } catch (e) {
    console.error('加载生词本失败:', e)
  } finally {
    isLoadingVocabulary.value = false
  }
}

// 加载历史文章
function loadHistoryArticle(article) {
  emit('load-article', article)
}

// 打开阅读历史页面
function openHistoryPage() {
  emit('open-subpage', 'history')
}

// 打开生词本页面
function openVocabularyPage() {
  emit('open-subpage', 'vocabulary')
}

// 播放单词发音
async function playWord(word) {
  try {
    const API_BASE = import.meta.env.PROD ? '/english' : ''
    
    // 使用 POST 方法
    const response = await fetch(`${API_BASE}/discovery/tts`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...auth.getAuthHeaders()
      },
      body: JSON.stringify({ text: word })
    })
    
    if (!response.ok) {
      throw new Error(`TTS 请求失败: ${response.status}`)
    }
    
    const blob = await response.blob()
    const audioUrl = URL.createObjectURL(blob)
    
    const audio = new Audio(audioUrl)
    audio.onended = () => URL.revokeObjectURL(audioUrl)
    audio.onerror = () => URL.revokeObjectURL(audioUrl)
    await audio.play()
  } catch (e) {
    console.error('播放发音失败:', e)
  }
}

// 获取话题图标
function getTopicIcon(topic) {
  const icons = {
    'tech': '🚀',
    'health': '💪',
    'culture': '🎨',
    'business': '📈',
    'travel': '✈️',
    'food': '🍜',
    'custom': '✨'
  }
  return icons[topic] || '📰'
}

// 格式化文章日期
function formatArticleDate(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now - date
  
  if (diff < 86400000) { // 24小时内
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  } else if (diff < 604800000) { // 7天内
    const days = Math.floor(diff / 86400000)
    return `${days}天前`
  } else {
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  }
}

// 监听登录状态
watch(() => auth.isLoggedIn, (isLoggedIn) => {
  if (isLoggedIn) {
    loadHistory()
  } else {
    historyList.value = []
  }
})

// 处理摘要更新事件
function handleSummaryUpdated(event) {
  const { conversationId, summary } = event.detail
  // 更新本地列表中的对应对话
  const item = historyList.value.find(h => h.id === conversationId)
  if (item) {
    item.title = summary
    console.log('侧边栏已更新摘要:', conversationId, summary)
  } else {
    // 如果本地没有这条记录，刷新整个列表
    loadHistory()
  }
}

// 初始化
onMounted(() => {
  // 恢复折叠状态
  const collapsed = localStorage.getItem('sidebar-collapsed')
  if (collapsed === 'true') {
    isCollapsed.value = true
  }
  
  if (auth.isLoggedIn) {
    loadHistory()
  }
  
  // 监听摘要更新事件
  window.addEventListener('conversation-summary-updated', handleSummaryUpdated)
})

// 监听视图切换，加载对应数据
watch(activeView, (newView) => {
  if (newView === 'discovery' && auth.isLoggedIn) {
    loadArticleHistory()
    loadVocabulary()
  }
})

// 组件卸载时移除事件监听
onUnmounted(() => {
  window.removeEventListener('conversation-summary-updated', handleSummaryUpdated)
})
</script>

<style scoped>
.history-sidebar {
  width: 280px;
  height: 100%;
  background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
  display: flex;
  flex-direction: column;
  position: relative;
  transition: width 0.3s ease;
  border-right: 1px solid rgba(255, 255, 255, 0.1);
}

.history-sidebar.collapsed {
  width: 60px;
}

/* 折叠按钮 - 加大尺寸便于点击 */
.collapse-btn {
  position: absolute;
  right: -18px;
  top: 20px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
  border: 3px solid #1a1a2e;
  color: white;
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(78, 205, 196, 0.4);
}

.collapse-btn:hover {
  transform: scale(1.15);
  box-shadow: 0 4px 12px rgba(78, 205, 196, 0.5);
}

.collapse-btn:active {
  transform: scale(0.95);
}

/* 侧边栏内容 */
.sidebar-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px;
  overflow-y: auto;
}

/* 新对话按钮 */
.new-chat-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
  border: none;
  border-radius: 12px;
  color: white;
  font-weight: 600;
  font-size: 0.95rem;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 16px;
}

.new-chat-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(78, 205, 196, 0.4);
}

.new-chat-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-icon {
  font-size: 1.1rem;
}

/* 🆕 模式选择器 */
.mode-selector {
  margin-bottom: 16px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.mode-label {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.mode-options {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.mode-option {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 10px 8px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}

.mode-option:hover {
  background: rgba(255, 255, 255, 0.08);
}

.mode-option.active {
  background: rgba(78, 205, 196, 0.15);
  border-color: rgba(78, 205, 196, 0.4);
}

.mode-icon {
  font-size: 1.2rem;
}

.mode-name {
  font-size: 0.8rem;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.8);
}

.mode-option.active .mode-name {
  color: #4ecdc4;
}

.mode-hint {
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.4);
  text-align: center;
}

/* 功能导航 */
.nav-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  margin-bottom: 16px;
}

.nav-tab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 12px;
  background: transparent;
  border: none;
  border-radius: 10px;
  color: rgba(255, 255, 255, 0.6);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.nav-tab:hover {
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.9);
}

.nav-tab.active {
  background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
  color: white;
  box-shadow: 0 2px 8px rgba(78, 205, 196, 0.3);
}

.nav-icon {
  font-size: 1rem;
}

.nav-text {
  font-size: 0.8rem;
}

/* 话题分类 */
.topic-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.topic-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
  padding-right: 4px;
}

.topic-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  color: rgba(255, 255, 255, 0.7);
}

.topic-item:hover {
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.95);
}

.topic-item.active {
  background: rgba(78, 205, 196, 0.15);
  border-left: 3px solid #4ecdc4;
  color: white;
}

.topic-icon {
  font-size: 1.2rem;
}

.topic-name {
  font-size: 0.9rem;
  font-weight: 500;
}

/* 自定义话题输入 */
.custom-topic-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.custom-topic-input {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.custom-input {
  flex: 1;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  color: white;
  font-size: 0.9rem;
  outline: none;
  transition: all 0.2s;
}

.custom-input:focus {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(78, 205, 196, 0.5);
}

.custom-input::placeholder {
  color: rgba(255, 255, 255, 0.4);
}

.custom-submit-btn {
  padding: 10px 14px;
  background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
  border: none;
  border-radius: 10px;
  color: white;
  font-size: 1rem;
  cursor: pointer;
  transition: all 0.2s;
}

.custom-submit-btn:hover:not(:disabled) {
  transform: scale(1.05);
  box-shadow: 0 2px 8px rgba(78, 205, 196, 0.4);
}

.custom-submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.custom-topic-hint {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.4);
  padding: 0 4px;
}

/* 搜索框 */
.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 10px;
  margin-bottom: 16px;
}

.search-icon {
  font-size: 0.9rem;
  opacity: 0.6;
}

.search-input {
  flex: 1;
  background: none;
  border: none;
  color: white;
  font-size: 0.9rem;
  outline: none;
}

.search-input::placeholder {
  color: rgba(255, 255, 255, 0.4);
}

/* 历史区域 */
.history-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.section-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.refresh-btn {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.9rem;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.refresh-btn:hover {
  opacity: 1;
}

.refresh-btn .spinning {
  display: inline-block;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 加载状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: rgba(255, 255, 255, 0.5);
  gap: 12px;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid rgba(255, 255, 255, 0.1);
  border-top-color: #4ecdc4;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  text-align: center;
}

.empty-icon {
  font-size: 3rem;
  margin-bottom: 12px;
  opacity: 0.3;
}

.empty-state p {
  margin: 0;
  color: rgba(255, 255, 255, 0.5);
  font-size: 0.9rem;
}

.empty-hint {
  margin-top: 8px !important;
  font-size: 0.8rem !important;
  opacity: 0.6;
}

/* 历史列表 */
.history-list {
  flex: 1;
  overflow-y: auto;
  margin: 0 -16px;
  padding: 0 8px;
}

.history-list::-webkit-scrollbar {
  width: 4px;
}

.history-list::-webkit-scrollbar-track {
  background: transparent;
}

.history-list::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
}

/* 分组 */
.history-group {
  margin-bottom: 16px;
}

.group-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.4);
  padding: 8px 12px 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* 历史项 */
.history-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 2px;
}

.history-item:hover {
  background: rgba(255, 255, 255, 0.08);
}

.history-item.active {
  background: rgba(78, 205, 196, 0.15);
  border-left: 3px solid #4ecdc4;
}

.item-icon {
  font-size: 1rem;
  opacity: 0.7;
}

.item-content {
  flex: 1;
  min-width: 0;
}

.item-title {
  font-size: 0.9rem;
  color: rgba(255, 255, 255, 0.9);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 2px;
}

.item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.item-time {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.4);
}

.item-level {
  font-size: 0.65rem;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
}

.level-a1 {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.level-a2 {
  background: rgba(246, 173, 85, 0.2);
  color: #f6ad55;
}

.level-b1 {
  background: rgba(99, 179, 237, 0.2);
  color: #63b3ed;
}

.level-b2 {
  background: rgba(56, 189, 248, 0.2);
  color: #38bdf8;
}

.level-c1 {
  background: rgba(72, 187, 120, 0.2);
  color: #48bb78;
}

.level-c2 {
  background: rgba(168, 85, 247, 0.2);
  color: #a855f7;
}

.item-menu {
  background: none;
  border: none;
  color: rgba(255, 255, 255, 0.4);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.history-item:hover .item-menu {
  opacity: 1;
}

.item-menu:hover {
  background: rgba(255, 255, 255, 0.1);
  color: white;
}

/* 底部用户信息：始终吸附在侧边栏底部（滚动历史时不消失） */
.sidebar-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  margin-top: 16px;
  position: sticky;
  bottom: 0;
  background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
}

.user-details {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-name {
  font-size: 0.9rem;
  color: white;
  font-weight: 500;
}

.user-score-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.user-level {
  font-size: 0.7rem;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
  width: fit-content;
}

.user-score {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.8);
  font-weight: 500;
}

.logout-btn {
  background: none;
  border: none;
  font-size: 1.2rem;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.2s;
  padding: 8px;
}

.logout-btn:hover {
  opacity: 1;
}

/* 迷你侧边栏 */
.mini-sidebar {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 0;
  height: 100%;
}

.mini-btn {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
  border: none;
  font-size: 1.2rem;
  cursor: pointer;
  transition: transform 0.2s;
}

.mini-btn:hover {
  transform: scale(1.1);
}

.mini-divider {
  width: 30px;
  height: 1px;
  background: rgba(255, 255, 255, 0.1);
  margin: 16px 0;
}

.mini-history {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
}

.mini-item {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.05);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.mini-item:hover {
  background: rgba(255, 255, 255, 0.1);
}

.mini-item.active {
  background: rgba(78, 205, 196, 0.2);
  border: 2px solid #4ecdc4;
}

.mini-footer {
  margin-top: auto;
}

.mini-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.2s;
}

.mini-avatar:hover {
  transform: scale(1.1);
}

/* 历史阅读记录 */
.history-articles-section,
.vocabulary-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.article-history-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 200px;
  overflow-y: auto;
}

.article-history-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  color: rgba(255, 255, 255, 0.7);
}

.article-history-item:hover {
  background: rgba(255, 255, 255, 0.08);
  color: white;
}

.article-topic {
  font-size: 1.1rem;
}

.article-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.article-title {
  font-size: 0.85rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.article-date {
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.4);
}

/* 生词本 */
.vocabulary-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 250px;
  overflow-y: auto;
}

.vocabulary-item {
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.word-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.word-text {
  font-size: 0.9rem;
  font-weight: 600;
  color: #4ecdc4;
}

.word-play-btn {
  background: none;
  border: none;
  font-size: 0.9rem;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.2s;
  padding: 2px 4px;
}

.word-play-btn:hover {
  opacity: 1;
}

.word-definition {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.6);
  line-height: 1.3;
}

.word-mastery {
  display: flex;
  gap: 4px;
  margin-top: 2px;
}

.mastery-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
}

.mastery-dot.filled {
  background: #4ecdc4;
}

.show-more {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.4);
  text-align: center;
  padding: 8px 0;
}

.empty-hint {
  font-size: 0.8rem;
  color: rgba(255, 255, 255, 0.4);
  text-align: center;
  padding: 12px 0;
}

.view-all-btn {
  background: none;
  border: none;
  color: #4ecdc4;
  font-size: 0.75rem;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: all 0.2s;
}

.view-all-btn:hover {
  background: rgba(78, 205, 196, 0.15);
}

/* 响应式 - 移动端适配 */
@media (max-width: 768px) {
  .history-sidebar {
    position: fixed;
    left: 0;
    top: 0;
    width: 85vw !important;
    max-width: 320px;
    height: 100vh;
    z-index: 1000;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
  }

  .history-sidebar.collapsed {
    width: 85vw !important;
    transform: translateX(-100%);
  }

  .history-sidebar:not(.collapsed) {
    transform: translateX(0);
  }

  /* 移动端折叠按钮 - 更大更明显 */
  .collapse-btn {
    right: -24px;
    width: 48px;
    height: 48px;
    font-size: 20px;
    border-width: 3px;
  }

  /* 折叠时按钮固定在屏幕左边 */
  .history-sidebar.collapsed .collapse-btn {
    position: fixed;
    left: 8px;
    right: auto;
    top: 12px;
    border-radius: 12px;
    background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
  }

  /* 遮罩层 - 点击关闭侧边栏 */
  .history-sidebar:not(.collapsed)::after {
    content: '';
    position: fixed;
    left: 100%;
    top: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(0, 0, 0, 0.5);
    z-index: -1;
  }

  /* 隐藏迷你侧边栏 */
  .mini-sidebar {
    display: none !important;
  }
}
</style>

