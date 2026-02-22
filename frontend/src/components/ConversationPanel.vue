<template>
  <div class="conversation-panel">
    <div class="messages-container" ref="messagesContainer">
      <!-- 空状态 -->
      <div v-if="conversation.messages.length === 0" class="empty-state">
        <div class="empty-icon">🎤</div>
        <h3>开始英语对话练习</h3>
        <p>点击下方「开始对话」即可开始</p>
        <div class="empty-tips">
          <div class="tip">🤖 自动对话模式：直接说话，无需按钮</div>
          <div class="tip">📊 AI 会实时评估你的口语表达</div>
          <div class="tip">📝 获取详细的语法纠错和建议</div>
        </div>
      </div>
      
      <!-- 消息列表 -->
      <TransitionGroup name="message" tag="div" class="messages-list">
        <div 
          v-for="(message, index) in conversation.messages" 
          :key="message.id || index"
          class="message-wrapper"
          :class="{ 'highlighted': message.messageRoundId && conversation.highlightedMessageId === message.messageRoundId }"
          :data-round-id="message.messageRoundId"
        >
          <!-- 消息气泡 -->
          <div 
            class="message"
            :class="[message.role, { streaming: message.streaming, recording: message.recording }]"
          >
            <div class="message-avatar">
              {{ message.role === 'user' ? '👤' : '🤖' }}
            </div>
            <div class="message-content">
              <div class="message-bubble">
                <!-- 🆕 录音/听写状态：录音中或等待ASR结果时显示声波 -->
                <template v-if="message.recording || (message.streaming && !message.content)">
                  <div class="typing-wave">
                    <span class="dot"></span>
                    <span class="dot"></span>
                    <span class="dot"></span>
                  </div>
                </template>
                <!-- 内容显示区域 -->
                <template v-else-if="message.content">
                  {{ message.content }}
                  <span v-if="message.streaming" class="cursor">|</span>
                </template>
                <!-- 🆕 空内容兜底：不显示空气泡 -->
              </div>
              <div class="message-time">
                {{ formatTime(message.timestamp) }}
              </div>
            </div>
          </div>
          
          <!-- AI 消息的翻译区域 -->
          <div v-if="message.role === 'assistant' && !message.streaming && message.content" class="translation-area">
            <!-- 已有翻译：显示翻译内容 -->
            <div v-if="message.translation" class="translation-inline">
              <span class="translation-label">🇨🇳</span>
              <span class="translation-text">{{ message.translation }}</span>
            </div>
            <!-- 正在翻译：显示加载状态 -->
            <div v-else-if="message.translating" class="translation-loading">
              <span class="loading-spinner-small"></span>
              <span>翻译中...</span>
            </div>
            <!-- 没有翻译：显示翻译按钮 -->
            <button v-else class="translate-btn" @click="handleTranslate(message.id)">
              🌐 翻译
            </button>
          </div>
          
          <!-- 用户消息的评估指示器 - 暂时隐藏 -->
          <!-- <div v-if="message.role === 'user' && message.evaluation" class="eval-indicator">
            <span class="eval-score" :class="getScoreClass(message.evaluation.overall_score)">
              {{ message.evaluation.overall_score }}分
            </span>
            <span class="eval-level" :class="getLevelClass(message.evaluation.cefr_level)">{{ message.evaluation.cefr_level }}</span>
          </div> -->
          
          <!-- 评估等待指示器 - 暂时隐藏 -->
          <!-- <div v-else-if="message.role === 'user' && !message.recording && !message.evaluation && !message.evaluationSkipped && message.content" class="eval-pending">
            <span class="pending-dot"></span>
            <span>评估中...</span>
          </div> -->
        </div>
      </TransitionGroup>
    </div>
    
    <!-- 🆕 性能指标面板（调试用） -->
    <div v-if="showPerformancePanel && conversation.latency" class="performance-panel">
      <div class="perf-header">
        <span>⚡ 性能指标</span>
        <button class="close-btn" @click="showPerformancePanel = false">×</button>
      </div>
      <div class="perf-metrics">
        <!-- 基础指标 -->
        <div class="metric" v-if="conversation.latency.ttft_ms">
          <span class="label">TTFT</span>
          <span class="value" :class="getLatencyClass(conversation.latency.ttft_ms)">
            {{ conversation.latency.ttft_ms }}ms
          </span>
        </div>
        <div class="metric" v-if="conversation.latency.llm_ms">
          <span class="label">LLM</span>
          <span class="value">{{ conversation.latency.llm_ms }}ms</span>
        </div>
        <div class="metric" v-if="conversation.latency.tts_ms">
          <span class="label">TTS</span>
          <span class="value">{{ conversation.latency.tts_ms }}ms</span>
        </div>
        <div class="metric total" v-if="conversation.latency.total_ms">
          <span class="label">总计</span>
          <span class="value">{{ conversation.latency.total_ms }}ms</span>
        </div>
        
        <!-- 🆕 详细性能指标（来自 metrics 对象） -->
        <template v-if="conversation.latency.metrics">
          <div class="metric-divider"></div>
          <div class="metric" v-if="conversation.latency.metrics.asr_latency_ms">
            <span class="label">ASR</span>
            <span class="value" :class="getLatencyClass(conversation.latency.metrics.asr_latency_ms)">
              {{ conversation.latency.metrics.asr_latency_ms }}ms
            </span>
          </div>
          <div class="metric" v-if="conversation.latency.metrics.llm_ttft_ms">
            <span class="label">LLM首Token</span>
            <span class="value" :class="getLatencyClass(conversation.latency.metrics.llm_ttft_ms)">
              {{ conversation.latency.metrics.llm_ttft_ms }}ms
            </span>
          </div>
          <div class="metric" v-if="conversation.latency.metrics.tts_first_chunk_ms">
            <span class="label">TTS首块</span>
            <span class="value" :class="getLatencyClass(conversation.latency.metrics.tts_first_chunk_ms)">
              {{ conversation.latency.metrics.tts_first_chunk_ms }}ms
            </span>
          </div>
          <div class="metric total" v-if="conversation.latency.metrics.total_latency_ms">
            <span class="label">端到端</span>
            <span class="value">{{ conversation.latency.metrics.total_latency_ms }}ms</span>
          </div>
        </template>
      </div>
    </div>
    
    <!-- 底部：录音控制区 -->
    <div class="input-area">
      <!-- 处理状态 -->
      <div v-if="conversation.isProcessing || conversation.isThinking" class="processing-indicator" :class="{ thinking: conversation.isThinking }">
        <div class="processing-spinner" :class="{ 'thinking-pulse': conversation.isThinking }"></div>
        <span>{{ conversation.isThinking ? '⏳ AI 深度思考中...' : 'AI 正在处理...' }}</span>
      </div>
      <!-- 底部控制区 -->
      <div v-else class="record-section">
        <div v-if="conversation.listenHint" class="listen-hint">{{ conversation.listenHint }}</div>
        <!-- 调试录音状态提示（自动开启/结束，上传到服务器） -->
        <div v-if="isDebugRecording" class="debug-record-hint">
          🎧 调试录音中… 结束对话后自动上传到服务器
        </div>
        <!-- 底部操作区：左侧评估，右侧开始/结束，对齐在同一行 -->
        <div class="bottom-bar">
          <!-- 小屏/平板：评估按钮（次级操作） -->
          <button 
            v-if="isEvalOverlay && openEvalSidebar"
            class="eval-btn"
            @click="openEvalSidebar()"
            title="查看口语评估与纠错"
          >
            📝 评估
            <span v-if="conversation.pendingEvaluations" class="eval-badge">{{ conversation.pendingEvaluations }}</span>
          </button>
          <!-- 统一工具栏（主操作：开始 / 继续 / 结束） -->
          <div class="unified-toolbar">
            <div class="toolbar-main">
          <!-- 没有对话时 或 正在创建中：开始按钮 -->
          <!-- 🔧 修复：starting 时也显示此按钮，避免闪烁到"继续对话" -->
          <button 
            v-if="!conversation.hasConversation || starting"
            class="action-btn primary"
            @click="startNewConversation"
            :disabled="starting"
          >
            <span class="action-icon">🎤</span>
            <span class="action-text">{{ starting ? '创建中...' : '开始对话' }}</span>
          </button>
          
          <!-- 有对话但未连接（且不在创建中）：继续按钮 -->
          <button 
            v-else-if="!conversation.isConnected && !starting"
            class="action-btn primary"
            @click="continueCurrentConversation"
            :disabled="continuing"
          >
            <span class="action-icon">🔄</span>
            <span class="action-text">{{ continuing ? '连接中...' : '继续对话' }}</span>
          </button>
          
          <!-- 已连接：状态/结束按钮 -->
          <template v-else>
            <button 
              class="status-end-btn"
              :class="{ 
                speaking: isSpeaking, 
                'ai-speaking': conversation.isAISpeaking,
                recording: !conversation.isAutoMode && conversation.isRecording
              }"
              @click="conversation.isAutoMode ? endCurrentConversation() : handleRecordClick()"
              :title="conversation.isAutoMode ? '点击结束对话' : (conversation.isRecording ? '停止录音' : '点击录音')"
            >
              <span class="status-icon">{{ getStatusIcon }}</span>
              <span class="status-text">{{ getStatusText }}</span>
            </button>
            
            <!-- 练习模式：手动开始下一轮按钮 -->
            <button 
              v-if="!conversation.isAutoMode && !conversation.isAISpeaking && !isSpeaking && !conversation.isRecording"
              class="next-turn-btn"
              @click="startNextTurn"
              title="点击开始下一轮录音"
            >
              🎤 开始录音
            </button>
          </template>
            </div>
          </div>
        </div> <!-- /bottom-bar -->
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted, inject, Transition } from 'vue'
import { useConversationStore } from '../stores/conversation'
import { useAuthStore } from '../stores/auth'
import { useVAD } from '../composables/useVAD'
import { useBreakpoint } from '../composables/useBreakpoint'

const conversation = useConversationStore()
const auth = useAuthStore()
const { isEvalOverlay } = useBreakpoint()
const openEvalSidebar = inject('openEvalSidebar', null)
const messagesContainer = ref(null)
const starting = ref(false)
const continuing = ref(false)
const showPerformancePanel = ref(false)  // 性能面板（调试用），默认隐藏

// 🧪 前端调试录音：连接时自动开启，断开时自动结束并上传到服务器
const API_BASE = import.meta.env.PROD ? '/english' : ''
const isDebugRecording = ref(false)
let debugMediaRecorder = null
let debugChunks = []
let debugStream = null

// 🆕 根据延迟值返回样式类
function getLatencyClass(ms) {
  if (ms < 500) return 'good'
  if (ms < 1000) return 'medium'
  return 'slow'
}

// 🆕 VAD 自动对话模式
const {
  isVADReady,
  isListening,
  isSpeaking,
  isAISpeaking,
  error: vadError,
  initVAD,
  startListening,
  stopListening,
  pauseVAD,
  resumeVAD,
  destroyVAD,
  setCallbacks,
  float32ToInt16,
  setupDeviceChangeListener,  // 🆕 设备变更监听
} = useVAD()

async function startDebugRecording() {
  if (isDebugRecording.value || !navigator.mediaDevices?.getUserMedia) return
  try {
    debugStream = await navigator.mediaDevices.getUserMedia({
      audio: { noiseSuppression: true, echoCancellation: true },
    })
    debugChunks = []
    const opts = { mimeType: 'audio/webm;codecs=opus' }
    debugMediaRecorder = new MediaRecorder(debugStream, opts)
    debugMediaRecorder.ondataavailable = (e) => {
      if (e.data?.size > 0) debugChunks.push(e.data)
    }
    debugMediaRecorder.onstop = async () => {
      if (debugChunks.length === 0) {
        cleanupDebugRecording()
        return
      }
      const blob = new Blob(debugChunks, { type: 'audio/webm' })
      const uid = (auth.userId || auth.username || 'unknown').toString()
      const cid = (conversation.conversationId || '').toString()
      const form = new FormData()
      form.append('file', blob, 'debug.webm')
      form.append('user_id', uid)
      form.append('conversation_id', cid)
      try {
        const res = await fetch(`${API_BASE}/api/debug-recording`, {
          method: 'POST',
          body: form,
        })
        const data = await res.json()
        if (data.status === 'ok') {
          console.log('[调试录音] 已保存到服务器:', data.filename)
        } else {
          console.warn('[调试录音] 上传失败:', data)
        }
      } catch (e) {
        console.error('[调试录音] 上传失败:', e)
      }
      cleanupDebugRecording()
    }
    debugMediaRecorder.start()
    isDebugRecording.value = true
  } catch (e) {
    console.error('调试录音启动失败:', e)
    cleanupDebugRecording()
  }
}

function stopDebugRecording() {
  if (debugMediaRecorder && debugMediaRecorder.state !== 'inactive') {
    debugMediaRecorder.stop()
  } else {
    cleanupDebugRecording()
  }
}

function cleanupDebugRecording() {
  if (debugStream) {
    debugStream.getTracks().forEach((t) => t.stop())
    debugStream = null
  }
  debugMediaRecorder = null
  debugChunks = []
  isDebugRecording.value = false
}

// 计算属性
const canRecord = computed(() => {
  return conversation.hasConversation && 
         conversation.isConnected && 
         !conversation.isProcessing
})

const recordHintText = computed(() => {
  if (!conversation.isConnected) return '未连接'
  if (conversation.isProcessing) return '处理中...'
  if (conversation.isRecording) return '点击停止或按空格键'
  return '点击开始或按空格键'
})

// 🆕 自动模式提示文本
const autoModeHintText = computed(() => {
  if (!conversation.isConnected) return '未连接'
  if (conversation.isProcessing) return '处理中...'
  
  if (conversation.isAutoMode) {
    if (conversation.isAISpeaking) return 'AI 正在说话，请稍候'
    if (isSpeaking.value) return '正在录音...'
    if (isListening.value) return '随时开始说话'
    return '正在初始化...'
  }
  
  if (conversation.isRecording) return '点击停止或按空格键'
  return '点击开始或按空格键'
})

// 🆕 切换自动/手动模式（由侧边栏调用，通过 store 的 isAutoMode 变化触发）
async function toggleMode() {
  conversation.toggleAutoMode()
  
  if (conversation.isAutoMode) {
    // 切换到对话模式，启动 VAD
    await startAutoListening()
  } else {
    // 切换到练习模式，停止 VAD
    stopAutoListening()
  }
}

// 🆕 练习模式：手动开始下一轮录音
async function startNextTurn() {
  if (conversation.isAutoMode) return  // 对话模式不需要手动开始
  
  console.log('[练习模式] 手动开始下一轮')
  
  // 启动 VAD 进行录音
  await startAutoListening()
}

// 监听模式变化（侧边栏切换时触发）
watch(() => conversation.isAutoMode, async (isAuto) => {
  if (conversation.isConnected) {
    if (isAuto) {
      await startAutoListening()
    } else {
      stopAutoListening()
    }
  }
})

// 🧪 调试录音：连接时自动开始，断开时自动结束并保存（文件名含用户ID）
watch(() => conversation.isConnected, (connected) => {
  if (connected) {
    startDebugRecording()
  } else {
    stopDebugRecording()
  }
})

// 根据分数返回样式类（6档，对应CEFR等级）
function getScoreClass(score) {
  if (score >= 90) return 'score-c2'   // C2: 金色
  if (score >= 75) return 'score-c1'   // C1: 紫色
  if (score >= 60) return 'score-b2'   // B2: 深绿
  if (score >= 45) return 'score-b1'   // B1: 蓝色
  if (score >= 25) return 'score-a2'   // A2: 橙色
  return 'score-a1'                     // A1: 红色
}

// 根据等级返回样式类
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

// 键盘事件处理
function handleKeyDown(e) {
  // 空格键统一控制
  if (e.code === 'Space' && !e.repeat) {
    // 避免在输入框中触发
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
      return
    }
    e.preventDefault()
    
    // 根据当前状态执行不同操作
    if (conversation.isRecording) {
      // 正在录音 → 停止录音
      conversation.stopRecording()
    } else if (conversation.isProcessing) {
      // 正在处理中 → 忽略
      return
    } else if (!conversation.hasConversation) {
      // 没有对话 → 开始新对话
      if (!starting.value) {
        startNewConversation()
      }
    } else if (!conversation.isConnected) {
      // 有对话但未连接 → 继续对话
      if (!continuing.value) {
        continueCurrentConversation()
      }
    } else {
      // 已连接 → 开始录音
      conversation.startRecording()
    }
  }
}

// 🆕 初始化 VAD 自动对话模式（双阈值系统）
async function initAutoMode() {
  if (!conversation.isAutoMode) {
    console.log('[AutoMode] 自动模式已禁用')
    return
  }
  
  // 设置 VAD 回调（双阈值系统）
  setCallbacks({
    onSpeechStart: () => {
      console.log('[AutoMode] VAD: 说话开始')
      conversation.handleVADSpeechStart()
    },
    onSpeechEnd: () => {
      // 注意：这个回调现在由双阈值系统内部处理
      // 只在 onConfirmEnd 触发后才会调用
      console.log('[AutoMode] VAD: 说话结束（长阈值确认）')
      conversation.handleVADSpeechEnd()
    },
    onAudioFrame: (frame) => {
      // 发送音频帧到 WebSocket
      conversation.sendAudioFrame(frame)
    },
    // 🆕 打断回调（学习自 UserGenie）
    // 当用户说话达到 0.5秒（17帧）时触发，执行打断 AI
    onInterrupt: () => {
      console.log('[AutoMode] VAD: 帧数达到阈值，触发打断')
      conversation.handleVADInterrupt()
    },
    // 🆕 误触发回调（语音太短）
    // 清理空用户消息 + 通知后端取消录音
    onMisfire: (frameCount) => {
      console.log('[AutoMode] VAD: 误触发，帧数=' + frameCount)
      conversation.handleVADMisfire(frameCount)
    },
    // 🆕 双阈值回调
    onSpeculativeStt: () => {
      // 短阈值触发（500ms）：预启动 STT
      console.log('[AutoMode] 短阈值触发，发送 speculative_stt')
      conversation.sendSpeculativeStt()
    },
    onConfirmEnd: () => {
      // 长阈值触发（1200ms）：确认用户说完
      console.log('[AutoMode] 长阈值确认，发送 confirm_end')
      conversation.sendConfirmEnd()
    },
    onCancelStt: () => {
      // 用户在等待期间继续说话：取消预启动
      console.log('[AutoMode] 用户继续说话，发送 cancel_stt')
      conversation.sendCancelStt()
    }
  })
  
  // 初始化 VAD
  const success = await initVAD()
  if (success) {
    console.log('[AutoMode] VAD 初始化成功（双阈值模式）')
    // 🆕 学习自 UserGenie: 设置设备变更监听（麦克风热插拔）
    setupDeviceChangeListener()
  } else {
    console.error('[AutoMode] VAD 初始化失败:', vadError.value)
  }
}

// 🆕 启动自动监听
async function startAutoListening() {
  if (!isVADReady.value) {
    await initAutoMode()
  }
  
  if (isVADReady.value) {
    await startListening()
    console.log('[AutoMode] 开始自动监听')
  }
}

// 🆕 停止自动监听
function stopAutoListening() {
  stopListening()
  console.log('[AutoMode] 停止自动监听')
}

// 🆕 监听 AI 说话状态，控制 VAD 暂停/恢复
watch(() => conversation.isAISpeaking, (speaking) => {
  if (conversation.isAutoMode && isListening.value) {
    if (speaking) {
      pauseVAD()
    } else {
      resumeVAD()
    }
  }
})

// 🆕 监听连接状态，自动启动/停止 VAD
watch(() => conversation.isConnected, async (connected) => {
  if (conversation.isAutoMode) {
    if (connected) {
      // 延迟启动 VAD，等待初始问题播放完毕
      setTimeout(async () => {
        await startAutoListening()
      }, 2000)  // 2秒后启动 VAD
    } else {
      stopAutoListening()
    }
  }
})

// 挂载时添加键盘监听
onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
  
  // 🆕 如果已连接且是自动模式，启动 VAD
  if (conversation.isConnected && conversation.isAutoMode) {
    initAutoMode().then(() => {
      startAutoListening()
    })
  }
})

// 卸载时移除监听
onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
  
  // 🆕 清理 VAD
  destroyVAD()
})

// 格式化时间（显示到秒）
function formatTime(date) {
  if (!date) return ''
  const d = new Date(date)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

// 开始新对话
async function startNewConversation() {
  starting.value = true
  await conversation.startConversation()
  starting.value = false
}

// 继续历史对话
async function continueCurrentConversation() {
  continuing.value = true
  await conversation.continueConversation()
  continuing.value = false
}

// 结束当前对话
function endCurrentConversation() {
  // 停止 VAD 监听
  if (isListening.value) {
    stopListening()
  }
  // 断开 WebSocket 连接
  conversation.disconnect()
}

// 状态图标（合并状态显示和结束功能）
const getStatusIcon = computed(() => {
  if (conversation.isAutoMode) {
    if (conversation.isAISpeaking) return '🤖'
    if (isSpeaking.value) return '🎙️'
    return '👂'  // 等待用户说话，点击可结束
  } else {
    // 手动模式
    return conversation.isRecording ? '⏹' : '🎤'
  }
})

// 状态文本
const getStatusText = computed(() => {
  if (conversation.isAutoMode) {
    if (conversation.isAISpeaking) return 'AI回复中'
    if (isSpeaking.value) return '聆听中'
    return '点击结束'  // 提示用户可以点击结束
  } else {
    return conversation.isRecording ? '停止' : '录音'
  }
})

// 录音控制
function handleRecordClick() {
  conversation.toggleRecording()
}

// 翻译 AI 回复
function handleTranslate(messageId) {
  conversation.translateMessage(messageId)
}

// 滚动到底部的函数
async function scrollToBottom() {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTo({
      top: messagesContainer.value.scrollHeight,
      behavior: 'smooth'
    })
  }
}

// 消息数量变化时滚动
watch(() => conversation.messages.length, scrollToBottom)

// 监听消息内容变化（流式输出、评估结果）
watch(
  () => conversation.messages.map(m => ({
    content: m.content,
    assessment: m.assessment,
    translation: m.translation
  })),
  scrollToBottom,
  { deep: true }
)
</script>

<style scoped>
.conversation-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  position: relative;
}

/* 🆕 性能指标面板 */
.performance-panel {
  position: absolute;
  top: 10px;
  right: 10px;
  background: rgba(0, 0, 0, 0.85);
  border-radius: 8px;
  padding: 10px 14px;
  z-index: 100;
  min-width: 140px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(8px);
}

.perf-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  color: #a0aec0;
  font-size: 0.75rem;
  font-weight: 600;
}

.perf-header .close-btn {
  background: none;
  border: none;
  color: #718096;
  cursor: pointer;
  padding: 0 4px;
  font-size: 1rem;
}

.perf-header .close-btn:hover {
  color: #fff;
}

.perf-metrics {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.perf-metrics .metric {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.7rem;
}

.perf-metrics .metric .label {
  color: #718096;
}

.perf-metrics .metric .value {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  color: #e2e8f0;
}

.perf-metrics .metric .value.good {
  color: #48bb78;
}

.perf-metrics .metric .value.medium {
  color: #ecc94b;
}

.perf-metrics .metric .value.slow {
  color: #fc8181;
}

.perf-metrics .metric.total {
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px solid #4a5568;
}

.perf-metrics .metric.total .value {
  font-weight: 600;
  color: #63b3ed;
}

/* 🆕 性能指标分隔线 */
.metric-divider {
  height: 1px;
  background: #4a5568;
  margin: 6px 0;
}

/* 🆕 思考中动画增强 */
.processing-indicator.thinking {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.processing-spinner.thinking-pulse {
  animation: thinking-pulse 1.5s ease-in-out infinite;
}

@keyframes thinking-pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.2);
    opacity: 0.7;
  }
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-light);
}

.panel-header h2 {
  font-size: 1.1rem;
  margin: 0;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  text-align: center;
}

.empty-icon {
  font-size: 3rem;
  margin-bottom: 16px;
  opacity: 0.5;
}

.messages-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message {
  display: flex;
  gap: 12px;
  max-width: 85%;
}

.message.user {
  flex-direction: row-reverse;
  margin-left: auto;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  flex-shrink: 0;
}

.message.user .message-avatar {
  background: var(--primary-light);
}

.message-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.message.user .message-content {
  align-items: flex-end;
}

.message-bubble {
  padding: 12px 16px;
  border-radius: var(--radius-lg);
  background: var(--bg-tertiary);
  line-height: 1.5;
  word-break: break-word;
}

.message.user .message-bubble {
  background: linear-gradient(135deg, var(--primary), var(--primary-dark));
  color: white;
}

.message.assistant .message-bubble {
  border-bottom-left-radius: var(--radius-sm);
}

.message.user .message-bubble {
  border-bottom-right-radius: var(--radius-sm);
}

.message-time {
  font-size: 0.75rem;
  color: var(--text-muted);
}

/* 🆕 极简声波/输入中动画 */
.typing-wave {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 24px;
  padding: 0 4px;
}

.typing-wave .dot {
  width: 6px;
  height: 6px;
  background: currentColor;
  border-radius: 50%;
  animation: wave-dots 1.4s ease-in-out infinite;
  opacity: 0.6;
}

.typing-wave .dot:nth-child(1) { animation-delay: 0s; }
.typing-wave .dot:nth-child(2) { animation-delay: 0.2s; }
.typing-wave .dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes wave-dots {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}

/* 旧的录音指示器样式（保留以防万一，或者删除） */
.recording-indicator {
  display: inline-flex;
  gap: 4px;
  margin-right: 8px;
}

.recording-indicator .dot {
  width: 6px;
  height: 6px;
  background: currentColor;
  border-radius: 50%;
  animation: bounce 1.4s ease-in-out infinite;
}

.recording-indicator .dot:nth-child(2) {
  animation-delay: 0.2s;
}

.recording-indicator .dot:nth-child(3) {
  animation-delay: 0.4s;
}

/* 流式输出光标 */
.cursor {
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% { opacity: 0; }
}

/* 处理状态栏 */
.processing-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  background: var(--bg-tertiary);
  border-top: 1px solid var(--border-light);
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.processing-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* 动画 */
.message-enter-active {
  animation: slideUp var(--transition-normal) ease-out;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--transition-fast);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 消息包装器 */
.message-wrapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: all 0.2s;
}

/* 高亮状态（与侧边栏交互） */
.message-wrapper.highlighted {
  background: rgba(78, 205, 196, 0.08);
  border-radius: var(--radius-md);
  padding: 8px;
  margin: -8px;
  box-shadow: 0 0 0 2px rgba(78, 205, 196, 0.3);
}

/* AI 翻译样式 */
.translation-inline {
  margin-left: 48px;
  padding: 8px 12px;
  background: rgba(66, 153, 225, 0.08);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--primary);
  font-size: 0.85rem;
  color: var(--text-secondary);
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.translation-label {
  flex-shrink: 0;
}

.translation-text {
  line-height: 1.5;
}

/* 翻译区域 */
.translation-area {
  margin-left: 48px;
}

/* 翻译按钮 */
.translate-btn {
  padding: 4px 12px;
  font-size: 0.8rem;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-full);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.translate-btn:hover {
  background: var(--primary-light);
  border-color: var(--primary);
  color: var(--primary-dark);
}

/* 翻译加载状态 */
.translation-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.8rem;
  color: var(--text-muted);
  padding: 4px 0;
}

.loading-spinner-small {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* 用户消息的评估指示器 */
.eval-indicator {
  margin-left: auto;
  margin-right: 48px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  font-size: 0.8rem;
}

.eval-score {
  font-weight: 600;
}

/* CEFR 等级对应的分数颜色 */
.eval-score.score-c2 { color: #FFD700; }  /* C2: 金色 */
.eval-score.score-c1 { color: #9B59B6; }  /* C1: 紫色 */
.eval-score.score-b2 { color: #27AE60; }  /* B2: 深绿 */
.eval-score.score-b1 { color: #3498DB; }  /* B1: 蓝色 */
.eval-score.score-a2 { color: #F39C12; }  /* A2: 橙色 */
.eval-score.score-a1 { color: #E74C3C; }  /* A1: 红色 */

.eval-level {
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-size: 0.7rem;
  font-weight: 600;
}

/* 6种 CEFR 等级颜色 */
.eval-level.level-a1 { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
.eval-level.level-a2 { background: rgba(246, 173, 85, 0.2); color: #f6ad55; }
.eval-level.level-b1 { background: rgba(99, 179, 237, 0.2); color: #63b3ed; }
.eval-level.level-b2 { background: rgba(56, 189, 248, 0.2); color: #38bdf8; }
.eval-level.level-c1 { background: rgba(72, 187, 120, 0.2); color: #48bb78; }
.eval-level.level-c2 { background: rgba(168, 85, 247, 0.2); color: #a855f7; }

/* 评估等待中指示器 */
.eval-pending {
  margin-left: auto;
  margin-right: 48px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  color: var(--text-muted);
}

.pending-dot {
  width: 6px;
  height: 6px;
  background: var(--primary);
  border-radius: 50%;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}

/* 底部输入区域 */
.input-area {
  position: relative;
  padding: 20px;
  border-top: 1px solid var(--border-light);
  background: var(--bg-secondary);
}

.processing-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 12px;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.record-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 调试录音状态提示 */
.debug-record-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
  text-align: center;
  padding: 4px 0;
}

.start-btn {
  padding: 14px 32px;
  font-size: 1rem;
}

.record-btn {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, var(--secondary), var(--secondary-dark));
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--transition-normal);
  box-shadow: 0 4px 16px rgba(78, 205, 196, 0.35);
}

.record-btn:hover:not(.disabled) {
  transform: scale(1.08);
  box-shadow: 0 6px 20px rgba(78, 205, 196, 0.45);
}

.record-btn.recording {
  background: linear-gradient(135deg, var(--error), #E53E3E);
  box-shadow: 0 4px 16px rgba(245, 101, 101, 0.35);
  animation: pulse-record 1.5s ease-in-out infinite;
}

.record-btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.record-icon {
  font-size: 1.8rem;
}

.record-hint {
  font-size: 0.85rem;
  color: var(--text-muted);
}

/* 🆕 听不清提示样式 */
.listen-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 10px 20px;
  margin-bottom: 8px;
  background: linear-gradient(135deg, rgba(255, 193, 7, 0.15), rgba(255, 193, 7, 0.05));
  border: 1px solid rgba(255, 193, 7, 0.3);
  border-radius: 12px;
  color: #e6a700;
  font-size: 0.9rem;
  font-weight: 500;
  animation: hint-bounce 0.3s ease-out;
}

@keyframes hint-bounce {
  0% { transform: translateY(-10px); opacity: 0; }
  100% { transform: translateY(0); opacity: 1; }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@keyframes pulse-record {
  0%, 100% { box-shadow: 0 4px 16px rgba(245, 101, 101, 0.35); }
  50% { box-shadow: 0 4px 24px rgba(245, 101, 101, 0.55); }
}

.btn-sm {
  padding: 6px 12px;
  font-size: 0.85rem;
}

/* 🆕 自动对话模式样式 */
.auto-mode-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 20px 32px;
  background: linear-gradient(135deg, rgba(78, 205, 196, 0.08), rgba(78, 205, 196, 0.02));
  border: 2px solid rgba(78, 205, 196, 0.2);
  border-radius: var(--radius-lg);
  transition: all 0.3s ease;
  min-width: 280px;
}

.auto-mode-indicator.speaking {
  background: linear-gradient(135deg, rgba(78, 205, 196, 0.15), rgba(78, 205, 196, 0.08));
  border-color: rgba(78, 205, 196, 0.5);
  box-shadow: 0 0 20px rgba(78, 205, 196, 0.2);
}

.auto-mode-indicator.ai-speaking {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(99, 102, 241, 0.05));
  border-color: rgba(99, 102, 241, 0.3);
}

.auto-mode-indicator.initializing {
  background: var(--bg-tertiary);
  border-color: var(--border);
}

.auto-mode-indicator.error {
  background: rgba(239, 68, 68, 0.08);
  border-color: rgba(239, 68, 68, 0.3);
}

.auto-mode-icon {
  font-size: 2.5rem;
  transition: all 0.3s ease;
}

.auto-mode-icon.speaking {
  animation: pulse-speaking 0.8s ease-in-out infinite;
}

.auto-mode-icon.ai-speaking {
  animation: pulse-ai 1.5s ease-in-out infinite;
}

@keyframes pulse-speaking {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.2); }
}

@keyframes pulse-ai {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(0.95); }
}

.auto-mode-text {
  font-size: 1.1rem;
  color: var(--text-secondary);
  font-weight: 500;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 3px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* ========== 统一工具栏 ========== */
.unified-toolbar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 10px 14px;
  position: relative;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(16px);
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2);
}

.toolbar-main {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

/* 底部操作区：评估 + 主按钮 同行对齐 */
.bottom-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
}

/* 评估按钮：次级操作，浅底 + 绿色描边 */
.eval-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px 14px;
  background: #ffffff;
  border: 1px solid rgba(78, 205, 196, 0.6);
  border-radius: 999px;
  color: var(--text-primary);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  position: relative;
  -webkit-tap-highlight-color: transparent;
  transition: all 0.2s ease;
}

.eval-btn:hover {
  background: rgba(78, 205, 196, 0.06);
  border-color: rgba(78, 205, 196, 0.8);
}

.eval-btn .eval-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: var(--primary);
  color: white;
  font-size: 0.7rem;
  line-height: 18px;
  text-align: center;
}

/* 让底部两颗按钮外观尺寸接近：参考顶部「未连接」pill */
.bottom-bar .action-btn.primary {
  padding: 6px 14px;
  font-size: 0.85rem;
  border-radius: var(--radius-full);
}

/* 开始/继续对话按钮 */
.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 20px;
  background: linear-gradient(135deg, rgba(78, 205, 196, 0.3) 0%, rgba(78, 205, 196, 0.15) 100%);
  border: 1px solid rgba(78, 205, 196, 0.4);
  border-radius: 14px;
  cursor: pointer;
  font-size: 0.95rem;
  color: rgba(255, 255, 255, 0.95);
  transition: all 0.25s ease;
}

.action-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, rgba(78, 205, 196, 0.4) 0%, rgba(78, 205, 196, 0.25) 100%);
  border-color: rgba(78, 205, 196, 0.6);
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(78, 205, 196, 0.25);
}

.action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.action-btn .action-icon {
  font-size: 1.2rem;
}

.action-btn .action-text {
  font-weight: 600;
}

/* 状态/结束按钮（合二为一） */
.status-end-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 12px;
  cursor: pointer;
  font-size: 0.9rem;
  color: rgba(255, 255, 255, 0.9);
  transition: all 0.2s ease;
}

.status-end-btn:hover {
  background: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.3);
}

.status-end-btn .status-icon {
  font-size: 1.1rem;
}

.status-end-btn .status-text {
  font-weight: 500;
  font-size: 0.85rem;
}

/* 聆听状态 */
.status-end-btn:not(.speaking):not(.ai-speaking):not(.recording) {
  background: rgba(255, 255, 255, 0.06);
}

/* 说话中状态 */
.status-end-btn.speaking {
  background: rgba(78, 205, 196, 0.2);
  border-color: rgba(78, 205, 196, 0.4);
  animation: pulse-speaking 1.5s ease-in-out infinite;
}

/* AI回复中状态 */
.status-end-btn.ai-speaking {
  background: rgba(147, 112, 219, 0.2);
  border-color: rgba(147, 112, 219, 0.4);
  animation: pulse-ai 1.5s ease-in-out infinite;
}

/* 录音中状态（手动模式） */
.status-end-btn.recording {
  background: rgba(239, 68, 68, 0.2);
  border-color: rgba(239, 68, 68, 0.4);
  animation: pulse-recording 1s ease-in-out infinite;
}

@keyframes pulse-speaking {
  0%, 100% { box-shadow: 0 0 0 0 rgba(78, 205, 196, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(78, 205, 196, 0); }
}

@keyframes pulse-ai {
  0%, 100% { box-shadow: 0 0 0 0 rgba(147, 112, 219, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(147, 112, 219, 0); }
}

@keyframes pulse-recording {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(239, 68, 68, 0); }
}

/* 🆕 练习模式：手动开始下一轮按钮 */
.next-turn-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  background: linear-gradient(135deg, rgba(78, 205, 196, 0.2) 0%, rgba(78, 205, 196, 0.1) 100%);
  border: 1px solid rgba(78, 205, 196, 0.4);
  border-radius: 12px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  color: #4ecdc4;
  transition: all 0.2s ease;
}

.next-turn-btn:hover {
  background: linear-gradient(135deg, rgba(78, 205, 196, 0.3) 0%, rgba(78, 205, 196, 0.2) 100%);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(78, 205, 196, 0.3);
}

/* VAD 声波动画 */
.vad-wave {
  display: flex;
  align-items: center;
  gap: 3px;
  height: 24px;
}

.vad-wave .bar {
  width: 4px;
  background: var(--primary);
  border-radius: 2px;
  animation: wave 1s ease-in-out infinite;
}

.vad-wave .bar:nth-child(1) { animation-delay: 0s; height: 8px; }
.vad-wave .bar:nth-child(2) { animation-delay: 0.1s; height: 16px; }
.vad-wave .bar:nth-child(3) { animation-delay: 0.2s; height: 24px; }
.vad-wave .bar:nth-child(4) { animation-delay: 0.3s; height: 16px; }
.vad-wave .bar:nth-child(5) { animation-delay: 0.4s; height: 8px; }

@keyframes wave {
  0%, 100% { transform: scaleY(0.5); }
  50% { transform: scaleY(1); }
}

/* ========== 移动端适配 ========== */
@media (max-width: 768px) {
  .conversation-panel {
    height: 100%;
  }

  .messages-container {
    padding: 12px;
  }

  /* 消息气泡适配 */
  .message {
    max-width: 90%;
  }

  .message-bubble {
    padding: 10px 14px;
    font-size: 0.95rem;
  }

  .message-avatar {
    width: 32px;
    height: 32px;
    font-size: 1rem;
  }

  /* 空状态 */
  .empty-state {
    padding: 20px;
  }

  .empty-icon {
    font-size: 2.5rem;
  }

  .empty-tips .tip {
    font-size: 0.85rem;
  }

  /* 底部输入区域 - 加大 */
  .input-area {
    padding: 16px;
    padding-bottom: calc(16px + env(safe-area-inset-bottom, 0px)); /* iOS 安全区 */
  }

  .bottom-bar {
    gap: 10px;
  }

  .eval-btn {
    font-size: 0.8rem;
    padding: 8px 12px;
  }

  /* 统一工具栏 - 移动端加大 */
  .unified-toolbar {
    padding: 12px 16px;
    border-radius: 24px;
    gap: 10px;
  }

  /* 开始/继续按钮 - 加大 */
  .action-btn {
    padding: 14px 24px;
    font-size: 1rem;
    border-radius: 16px;
  }

  .action-btn .action-icon {
    font-size: 1.4rem;
  }

  /* 状态按钮 - 加大 */
  .status-end-btn {
    padding: 14px 20px;
    border-radius: 14px;
    font-size: 1rem;
  }

  .status-end-btn .status-icon {
    font-size: 1.4rem;
  }

  /* 下一轮按钮 - 加大 */
  .next-turn-btn {
    padding: 14px 20px;
    font-size: 1rem;
    border-radius: 14px;
  }

  /* 性能面板 - 移动端隐藏或缩小 */
  .performance-panel {
    top: 8px;
    right: 8px;
    min-width: 120px;
    padding: 8px 10px;
    font-size: 0.65rem;
  }

  .perf-header {
    font-size: 0.7rem;
  }

  /* 翻译区域 */
  .translation-area {
    margin-left: 40px;
  }

  .translation-inline {
    margin-left: 40px;
    padding: 6px 10px;
    font-size: 0.8rem;
  }
}

/* 小屏手机进一步优化 */
@media (max-width: 375px) {
  .action-btn {
    padding: 12px 18px;
  }

  .status-end-btn {
    padding: 12px 16px;
  }

  .unified-toolbar {
    padding: 10px 12px;
  }
}
</style>

