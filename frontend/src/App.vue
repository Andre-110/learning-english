<template>
  <div class="app" :class="{ 'with-sidebar': auth.isLoggedIn }">
    <!-- 🆕 验证中显示加载状态（防止页面闪烁） -->
    <template v-if="auth.isVerifying">
      <div class="loading-screen">
        <div class="loading-content">
          <span class="loading-icon">🎤</span>
          <h2>LinguaCoach</h2>
          <div class="loading-spinner"></div>
          <p>正在加载...</p>
        </div>
      </div>
    </template>
    
    <!-- 未登录显示认证组件 -->
    <template v-else-if="!auth.isLoggedIn">
      <!-- 头部 -->
      <header class="header">
        <div class="header-content">
          <div class="logo">
            <span class="logo-icon">🎤</span>
            <h1>LinguaCoach</h1>
          </div>
          <p class="tagline">智能英语口语对话测评</p>
        </div>
      </header>
      
      <main class="main auth-main">
        <AuthPanel />
      </main>
    </template>
    
    <!-- 已登录显示带侧边栏的界面 -->
    <template v-else>
      <!-- 左侧：历史对话侧边栏 -->
      <HistorySidebar 
        ref="historySidebarRef"
        @view-change="handleViewChange"
        @topic-select="handleTopicSelect"
        @load-article="handleLoadArticle"
        @open-subpage="handleOpenSubpage"
      />
      
      <!-- 中间：主内容区 -->
      <div class="main-content main-content-with-eval">
        <!-- 顶部工具栏 -->
        <header class="toolbar">
          <div class="toolbar-left">
            <!-- 手机端：菜单按钮打开历史侧栏；手机端隐藏 logo 节省空间 -->
            <button v-if="isMobile" class="toolbar-icon-btn" @click="openHistorySidebar" title="历史对话" aria-label="打开历史">
              ☰
            </button>
            <div v-if="!isMobile" class="logo-mini">
              <span class="logo-icon">🎤</span>
              <span class="logo-text">LinguaCoach</span>
            </div>
          </div>
          
          <div class="toolbar-center">
            <!-- 对话模式：连接状态 -->
            <div class="connection-status" :class="{ connected: conversation.isConnected }">
              <span class="status-dot"></span>
              <span>{{ conversation.isConnected ? '已连接' : '未连接' }}</span>
            </div>
            <!-- 发现模式：当前模式标识 - 暂时隐藏
            <template v-if="currentView === 'discovery'">
              <div class="view-indicator">
                <span class="view-icon">🌟</span>
                <span>每日发现</span>
              </div>
            </template>
            -->
          </div>
          
          <div class="toolbar-right">
            <!-- 全局显示：退出登录按钮（无需下滑或展开侧边栏） -->
            <button
              class="toolbar-icon-btn"
              @click="auth.logout"
              title="退出登录"
              aria-label="退出登录"
            >
              🚪
            </button>
            <!-- AI 服务 + 语音风格选择 -->
            <VoiceStyleSelector />
          </div>
        </header>
        
        <!-- 主内容区域 -->
        <main class="chat-main">
          <!-- 对话模式 -->
          <ConversationPanel />
          <!-- 发现模式 - 暂时隐藏
          <DiscoveryPanel 
            v-if="currentView === 'discovery'"
            ref="discoveryPanelRef"
            :selected-topic="selectedTopic"
            :subpage="discoverySubpage"
            @article-read="handleArticleRead"
            @close-subpage="discoverySubpage = null"
          />
          -->
        </main>
      </div>
      
      <!-- 右侧边栏（Web 常驻；手机端通过按钮打开为浮层） -->
      <EvaluationSidebar 
        v-if="currentView === 'conversation'"
        :evaluations="conversation.evaluations"
        :pending-count="conversation.pendingEvaluations"
        :mobile-open="showEvalMobile"
        @close="showEvalMobile = false"
        @highlight-message="conversation.highlightMessage"
        @unhighlight-message="conversation.unhighlightMessage"
      />
    </template>

    <!-- 错误提示 -->
    <Transition name="toast">
      <div v-if="errorMessage" class="toast toast-error" @click="clearError">
        {{ errorMessage }}
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, provide } from 'vue'
import { useAuthStore } from './stores/auth'
import { useConversationStore } from './stores/conversation'
import { useBreakpoint } from './composables/useBreakpoint'
import AuthPanel from './components/AuthPanel.vue'
import ConversationPanel from './components/ConversationPanel.vue'
import HistorySidebar from './components/HistorySidebar.vue'
import EvaluationSidebar from './components/EvaluationSidebar.vue'
import VoiceStyleSelector from './components/VoiceStyleSelector.vue'
// 每日发现功能暂时隐藏
// import DiscoveryPanel from './components/DiscoveryPanel.vue'

const auth = useAuthStore()
const conversation = useConversationStore()
const { isMobile } = useBreakpoint()

const historySidebarRef = ref(null)
const showEvalMobile = ref(false)

function openHistorySidebar() {
  historySidebarRef.value?.open?.()
}

provide('openEvalSidebar', () => {
  showEvalMobile.value = true
})

// 当前视图模式 - 每日发现功能暂时隐藏，固定为对话模式
const currentView = ref('conversation')
// 以下变量暂时保留，便于后续恢复
const selectedTopic = ref(null)
const discoveryPanelRef = ref(null)
const discoverySubpage = ref(null)

// 错误消息
const errorMessage = computed(() => auth.error || conversation.error)

function clearError() {
  auth.error = null
  conversation.error = null
}

// 视图切换处理
function handleViewChange(view) {
  currentView.value = view
}

// 话题选择处理
function handleTopicSelect(topicId) {
  selectedTopic.value = topicId
}

// 文章阅读完成
function handleArticleRead(article) {
  console.log('文章阅读完成:', article.title)
}

// 加载历史文章
function handleLoadArticle(article) {
  console.log('加载历史文章:', article.id)
  // 切换到发现模式
  currentView.value = 'discovery'
  discoverySubpage.value = null // 退出子页面
  // 调用 DiscoveryPanel 的方法加载文章
  if (discoveryPanelRef.value) {
    discoveryPanelRef.value.loadHistoryArticle(article)
  }
}

// 打开子页面
function handleOpenSubpage(subpage) {
  console.log('打开子页面:', subpage)
  currentView.value = 'discovery'
  discoverySubpage.value = subpage
}

// 自动清除错误
watch(errorMessage, (msg) => {
  if (msg) {
    setTimeout(clearError, 5000)
  }
})

// 监听登录状态
watch(() => auth.isLoggedIn, async (isLoggedIn) => {
  if (isLoggedIn) {
    // 登录后加载用户画像
    await conversation.loadUserProfile()
  }
})

// 初始化
onMounted(async () => {
  await auth.verifyToken()
  if (auth.isLoggedIn) {
    // 加载用户画像
    await conversation.loadUserProfile()
  }
})
</script>

<style scoped>
.app {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
}

/* 🆕 加载屏幕（Token 验证时显示） */
.loading-screen {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--bg-primary) 0%, var(--bg-secondary) 100%);
}

.loading-content {
  text-align: center;
  color: var(--text-primary);
}

.loading-content .loading-icon {
  font-size: 4rem;
  display: block;
  margin-bottom: 16px;
  animation: pulse 2s infinite;
}

.loading-content h2 {
  font-size: 1.8rem;
  font-weight: 700;
  margin: 0 0 24px 0;
  background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.loading-content .loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--border-light);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}

.loading-content p {
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin: 0;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.1); }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.app.with-sidebar {
  flex-direction: row;
  height: 100vh;
  overflow: hidden;
}

/* 未登录时的头部 */
.header {
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
  color: white;
  padding: 20px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: var(--shadow-lg);
}

.header-content {
  display: flex;
  align-items: center;
  gap: 20px;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon {
  font-size: 2rem;
}

.logo h1 {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0;
}

.tagline {
  font-size: 0.9rem;
  opacity: 0.9;
  margin: 0;
}

.auth-main {
  flex: 1;
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

/* 已登录时的主内容区 */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-primary);
}

/* 带评估侧边栏时的主内容区 */
.main-content.main-content-with-eval {
  /* 减少宽度以容纳右侧评估侧边栏 */
}

/* 顶部工具栏 */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-light);
  min-height: 60px;
}

.toolbar-left {
  display: flex;
  align-items: center;
}

.logo-mini {
  display: flex;
  align-items: center;
  gap: 8px;
}

.logo-mini .logo-icon {
  font-size: 1.5rem;
}

.logo-mini .logo-text {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text-primary);
}

.toolbar-center {
  display: flex;
  align-items: center;
  gap: 16px;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 视图指示器 */
.view-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: linear-gradient(135deg, rgba(78, 205, 196, 0.15), rgba(78, 205, 196, 0.05));
  border: 1px solid rgba(78, 205, 196, 0.3);
  border-radius: var(--radius-full);
  font-size: 0.85rem;
  color: var(--secondary);
  font-weight: 500;
}

.view-icon {
  font-size: 1rem;
}

/* 侧边栏标题 */
.sidebar-title {
  font-size: 0.9rem;
  color: var(--text-secondary);
  font-weight: 500;
}

/* 连接状态 */
.connection-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--error);
  transition: background var(--transition-normal);
}

.connection-status.connected .status-dot {
  background: var(--success);
  box-shadow: 0 0 8px var(--success);
}

.connection-status.connected {
  color: var(--success);
}

/* 对话主区域 */
.chat-main {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
}

/* Toast 提示 */
.toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  padding: 12px 24px;
  border-radius: var(--radius-md);
  font-weight: 500;
  cursor: pointer;
  z-index: 1000;
  box-shadow: var(--shadow-lg);
}

.toast-error {
  background: var(--error);
  color: white;
}

.toast-enter-active,
.toast-leave-active {
  transition: all var(--transition-normal);
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(20px);
}

/* 响应式 - 移动端适配 */
@media (max-width: 768px) {
  .header {
    flex-direction: column;
    gap: 12px;
    text-align: center;
  }
  
  .header-content {
    flex-direction: column;
    gap: 8px;
  }
  
  /* 移动端工具栏 */
  .toolbar {
    flex-wrap: wrap;
    gap: 8px;
    padding: 10px 12px;
    min-height: 50px;
  }
  
  .toolbar-left {
    flex: 0;
  }
  
  .logo-mini .logo-text {
    display: none; /* 隐藏文字只显示图标 */
  }
  
  .toolbar-center {
    order: 3;
    width: 100%;
    justify-content: center;
  }
  
  .toolbar-right {
    flex: 1;
    justify-content: flex-end;
  }
  
  /* 移动端对话区域 */
  .chat-main {
    padding: 12px;
  }
  
  .service-select {
    font-size: 0.8rem;
    padding: 6px 10px;
  }

  /* 移动端主内容区全宽 */
  .main-content {
    width: 100vw;
  }
}

/* 手机端工具栏图标按钮 */
.toolbar-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 0;
  margin-right: 4px;
  border: none;
  border-radius: var(--radius-md);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 1.25rem;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.toolbar-icon-btn:hover {
  background: var(--border-light);
}
</style>
