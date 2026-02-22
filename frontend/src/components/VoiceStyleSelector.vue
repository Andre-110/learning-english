<template>
  <div class="ai-control-group">
    <!-- AI 服务选择器 -->
    <div class="service-selector">
      <select 
        v-model="selectedService" 
        class="service-select"
        @change="handleServiceChange"
        title="选择 AI 服务"
      >
        <option value="gpt4o-pipeline">🎯 GPT-4o</option>
        <option value="qwen-omni">🚀 Qwen3</option>
        <option value="realtime">⚡ Realtime</option>
        <option value="dashscope">📡 DashScope</option>
        <option value="openrouter">🌐 OpenRouter</option>
      </select>
    </div>
    
    <!-- 语音风格选择器 -->
    <div class="voice-style-selector" :class="{ 'is-open': isOpen }">
      <!-- 触发按钮 - 简洁设计 -->
      <button 
        class="trigger-btn"
        @click.stop="toggleDropdown"
        :title="`当前: ${currentStyleNameZh}`"
      >
        <span class="current-icon">{{ currentStyleIcon }}</span>
        <span class="current-label">{{ currentStyleNameZh }}</span>
        <svg class="arrow-icon" :class="{ rotated: isOpen }" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
        </svg>
      </button>

    <!-- 下拉菜单 -->
    <transition name="dropdown">
      <div v-if="isOpen" class="dropdown-panel">
        <!-- 标题 -->
        <div class="panel-header">
          <div class="header-title">
            <span class="header-icon">🎙️</span>
            <span>AI 语音风格</span>
          </div>
          <span class="header-hint">点击试听 · 选择切换</span>
        </div>
        
        <!-- 风格列表 -->
        <div class="style-grid">
          <div
            v-for="style in voiceStyles"
            :key="style.id"
            class="style-card"
            :class="{ 
              'is-selected': selectedStyleId === style.id,
              'is-playing': playingStyleId === style.id 
            }"
            @click="selectStyle(style)"
          >
            <!-- 选中指示器 -->
            <div class="selected-indicator" v-if="selectedStyleId === style.id">
              <svg viewBox="0 0 24 24" fill="currentColor">
                <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/>
              </svg>
            </div>
            
            <!-- 卡片内容 -->
            <div class="card-icon" :style="{ background: getStyleGradient(style.id) }">
              {{ getStyleIcon(style.id) }}
            </div>
            <div class="card-info">
              <div class="card-name">{{ style.name_zh }}</div>
              <div class="card-desc">{{ style.description_zh }}</div>
            </div>
            
            <!-- 试听按钮 -->
            <button 
              class="preview-btn"
              :class="{ playing: playingStyleId === style.id }"
              @click.stop="togglePreview(style.id)"
              :title="playingStyleId === style.id ? '停止' : '试听'"
            >
              <svg v-if="playingStyleId === style.id" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="4" width="4" height="16"/>
                <rect x="14" y="4" width="4" height="16"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="currentColor">
                <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </transition>
    
    <!-- 遮罩层 -->
    <div v-if="isOpen" class="backdrop" @click="isOpen = false"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useConversationStore } from '../stores/conversation'
import { useAuthStore } from '../stores/auth'

const conversation = useConversationStore()
const auth = useAuthStore()

const isOpen = ref(false)
const voiceStyles = ref([])
const selectedStyleId = ref('friendly')
const playingStyleId = ref(null)

// AI 服务选择
const selectedService = ref('gpt4o-pipeline')

// 音频播放器
let audioElement = null

// 风格图标映射
const styleIcons = {
  friendly: '🌟',
  professional: '📚',
  energetic: '⚡',
  calm: '🧘',
  storyteller: '📖',
  natural: '🎭'
}

// 风格渐变色
const styleGradients = {
  friendly: 'linear-gradient(135deg, #FF9A8B 0%, #FF6B6B 100%)',
  professional: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
  energetic: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
  calm: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
  storyteller: 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)',
  natural: 'linear-gradient(135deg, #a8edea 0%, #fed6e3 100%)'
}

// 预录制的 demo 音频路径
const audioBase = import.meta.env.PROD ? '/english' : ''
const previewAudioUrls = {
  friendly: `${audioBase}/audio/voice-preview-friendly.mp3`,
  professional: `${audioBase}/audio/voice-preview-professional.mp3`,
  energetic: `${audioBase}/audio/voice-preview-energetic.mp3`,
  calm: `${audioBase}/audio/voice-preview-calm.mp3`,
  storyteller: `${audioBase}/audio/voice-preview-storyteller.mp3`,
  natural: `${audioBase}/audio/voice-preview-natural.mp3`
}

const getStyleIcon = (id) => styleIcons[id] || '🎤'
const getStyleGradient = (id) => styleGradients[id] || styleGradients.friendly

const currentStyleIcon = computed(() => {
  return getStyleIcon(selectedStyleId.value)
})

const currentStyleNameZh = computed(() => {
  const style = voiceStyles.value.find(s => s.id === selectedStyleId.value)
  return style?.name_zh || '友好导师'
})

function toggleDropdown() {
  isOpen.value = !isOpen.value
  if (!isOpen.value) {
    stopPreview()
  }
}

function togglePreview(styleId) {
  if (playingStyleId.value === styleId) {
    stopPreview()
  } else {
    playPreview(styleId)
  }
}

function playPreview(styleId) {
  stopPreview()
  
  const audioUrl = previewAudioUrls[styleId]
  if (!audioUrl) {
    console.warn(`No preview audio for style: ${styleId}`)
    return
  }
  
  audioElement = new Audio(audioUrl)
  audioElement.volume = 0.8
  
  audioElement.onplay = () => {
    playingStyleId.value = styleId
  }
  
  audioElement.onended = () => {
    playingStyleId.value = null
  }
  
  audioElement.onerror = (e) => {
    console.warn(`Failed to load preview audio: ${audioUrl}`, e)
    playingStyleId.value = null
  }
  
  audioElement.play().catch(e => {
    console.warn('Audio play failed:', e)
    playingStyleId.value = null
  })
}

function stopPreview() {
  if (audioElement) {
    audioElement.pause()
    audioElement.currentTime = 0
    audioElement = null
  }
  playingStyleId.value = null
}

function selectStyle(style) {
  selectedStyleId.value = style.id
  // 不关闭下拉菜单，方便用户继续试听其他风格
  
  // 自动播放试音
  playPreview(style.id)
  
  conversation.setVoiceStyle(style.id)
  localStorage.setItem('voiceStyleId', style.id)
}

async function loadVoiceStyles() {
  try {
    const baseUrl = import.meta.env.PROD ? '/english' : ''
    const response = await fetch(`${baseUrl}/voice-style/list`)
    if (response.ok) {
      const data = await response.json()
      voiceStyles.value = data.styles
      
      const savedStyleId = localStorage.getItem('voiceStyleId')
      if (savedStyleId && data.styles.some(s => s.id === savedStyleId)) {
        selectedStyleId.value = savedStyleId
      } else {
        selectedStyleId.value = data.default_style_id || 'friendly'
      }
    }
  } catch (error) {
    console.error('Failed to load voice styles:', error)
    voiceStyles.value = [
      { id: 'friendly', name_zh: '友好导师', description_zh: '温暖鼓励，像耐心的朋友' },
      { id: 'professional', name_zh: '专业教师', description_zh: '清晰专业，像语言教师' },
      { id: 'energetic', name_zh: '活力教练', description_zh: '活力四射，保持你的投入' },
      { id: 'calm', name_zh: '沉稳向导', description_zh: '舒缓放松，减少焦虑' },
      { id: 'storyteller', name_zh: '故事讲述者', description_zh: '富有表现力，像讲故事' },
      { id: 'natural', name_zh: '自然对话', description_zh: '最像真人，日常闲聊风格' }
    ]
  }
}

// 切换 AI 服务
async function handleServiceChange() {
  try {
    // 同步到 conversation store 的 processingMode
    conversation.setProcessingMode(selectedService.value)
    
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
      const service = data.service || 'gpt4o-pipeline'
      selectedService.value = service
      // 同步到 conversation store
      conversation.setProcessingMode(service)
    }
  } catch (e) {
    console.error('加载服务设置失败:', e)
  }
}

onMounted(() => {
  loadVoiceStyles()
  loadCurrentService()
})

onUnmounted(() => {
  stopPreview()
})
</script>

<style scoped>
/* 控制组容器 */
.ai-control-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* AI 服务选择器 */
.service-selector {
  position: relative;
}

.service-select {
  padding: 8px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: 0.85rem;
  cursor: pointer;
  outline: none;
  transition: all 0.2s ease;
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;
  padding-right: 28px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23666' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
}

.service-select:hover {
  border-color: var(--primary);
}

.service-select:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(78, 205, 196, 0.15);
}

.service-select option {
  background: var(--bg-primary);
  color: var(--text-primary);
  padding: 8px;
}

.voice-style-selector {
  position: relative;
  z-index: 50;
}

/* 触发按钮 - 适配浅色工具栏 */
.trigger-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--text-primary);
  transition: all 0.2s ease;
}

.trigger-btn:hover {
  border-color: var(--primary);
  background: var(--bg-tertiary);
}

.voice-style-selector.is-open .trigger-btn {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(78, 205, 196, 0.15);
}

.current-icon {
  font-size: 1rem;
}

.current-label {
  font-weight: 500;
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.arrow-icon {
  width: 14px;
  height: 14px;
  opacity: 0.5;
  transition: transform 0.2s ease;
  stroke: var(--text-secondary);
}

.arrow-icon.rotated {
  transform: rotate(180deg);
}

/* 遮罩层 */
.backdrop {
  position: fixed;
  inset: 0;
  z-index: -1;
}

/* 下拉面板 - 向下展开 */
.dropdown-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 340px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  z-index: 100;
}

/* 面板头部 */
.panel-header {
  padding: 14px 16px;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-light);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 0.95rem;
  color: var(--text-primary);
}

.header-icon {
  font-size: 1.1rem;
}

.header-hint {
  display: block;
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 4px;
}

/* 风格网格 */
.style-grid {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
}

.style-grid::-webkit-scrollbar {
  width: 4px;
}

.style-grid::-webkit-scrollbar-track {
  background: transparent;
}

.style-grid::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 2px;
}

/* 风格卡片 */
.style-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s ease;
}

.style-card:hover {
  background: var(--bg-tertiary);
  border-color: var(--border);
  transform: translateX(2px);
}

.style-card.is-selected {
  background: rgba(78, 205, 196, 0.1);
  border-color: var(--primary);
}

.style-card.is-playing {
  background: rgba(34, 197, 94, 0.1);
  border-color: rgba(34, 197, 94, 0.5);
}

/* 选中指示器 */
.selected-indicator {
  position: absolute;
  top: 8px;
  right: 48px;
  width: 18px;
  height: 18px;
  background: var(--primary);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.selected-indicator svg {
  width: 10px;
  height: 10px;
  color: white;
}

/* 卡片图标 */
.card-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.3rem;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* 卡片信息 */
.card-info {
  flex: 1;
  min-width: 0;
}

.card-name {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.card-desc {
  font-size: 0.75rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 试听按钮 */
.preview-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.preview-btn svg {
  width: 16px;
  height: 16px;
  color: var(--text-secondary);
}

.preview-btn:hover {
  background: var(--border);
  transform: scale(1.05);
}

.preview-btn:hover svg {
  color: var(--text-primary);
}

.preview-btn.playing {
  background: var(--success);
  animation: pulse-glow 1.5s ease-in-out infinite;
}

.preview-btn.playing svg {
  color: white;
}

@keyframes pulse-glow {
  0%, 100% { 
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.4);
  }
  50% { 
    box-shadow: 0 0 0 8px rgba(34, 197, 94, 0);
  }
}

/* 下拉动画 */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-10px) scale(0.95);
}

/* 响应式 - 移动端适配 */
@media (max-width: 768px) {
  .ai-control-group {
    gap: 6px;
  }

  .service-select {
    padding: 6px 8px;
    font-size: 0.8rem;
    padding-right: 24px;
  }

  .trigger-btn {
    padding: 6px 10px;
    gap: 6px;
  }

  .current-label {
    max-width: 60px;
    font-size: 0.8rem;
  }

  .dropdown-panel {
    width: calc(100vw - 24px);
    right: -12px;
    max-height: 70vh;
  }

  .style-grid {
    max-height: 50vh;
  }

  .style-card {
    padding: 10px;
  }

  .card-icon {
    width: 36px;
    height: 36px;
    font-size: 1.1rem;
  }

  .card-name {
    font-size: 0.85rem;
  }

  .card-desc {
    font-size: 0.7rem;
  }

  .preview-btn {
    width: 40px;
    height: 40px;
  }

  .preview-btn svg {
    width: 18px;
    height: 18px;
  }
}

@media (max-width: 400px) {
  .dropdown-panel {
    width: calc(100vw - 16px);
    right: -8px;
  }

  .current-label {
    display: none; /* 极小屏只显示图标 */
  }
}
</style>
