<template>
  <div class="discovery-panel">
    <!-- 子页面：阅读历史 -->
    <div v-if="subpage === 'history'" class="subpage-container">
      <div class="subpage-header">
        <button class="back-btn" @click="emit('close-subpage')">← 返回</button>
        <h2 class="subpage-title">📚 阅读历史</h2>
        <button class="refresh-btn" @click="loadAllArticleHistory" :disabled="isLoadingHistory">
          <span :class="{ spinning: isLoadingHistory }">🔄</span>
        </button>
      </div>
      <div class="subpage-content">
        <div v-if="isLoadingHistory" class="loading-state">
          <div class="loading-spinner"></div>
          <span>加载中...</span>
        </div>
        <div v-else-if="allArticleHistory.length === 0" class="empty-state">
          <div class="empty-icon">📚</div>
          <h3>还没有阅读记录</h3>
          <p>开始阅读文章后，历史记录会显示在这里</p>
        </div>
        <div v-else class="history-grid">
          <div 
            v-for="article in allArticleHistory" 
            :key="article.id"
            class="history-card"
            @click="loadHistoryArticleAndClose(article)"
          >
            <div class="history-card-header">
              <span class="history-topic">{{ getTopicIcon(article.topic) }} {{ getTopicLabel(article.topic) }}</span>
              <span class="history-level" :class="getLevelClass(article.cefr_level)">{{ article.cefr_level }}</span>
            </div>
            <h3 class="history-title">{{ article.title }}</h3>
            <div class="history-meta">
              <span class="history-date">{{ formatDate(article.created_at) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 子页面：生词本 -->
    <div v-else-if="subpage === 'vocabulary'" class="subpage-container">
      <div class="subpage-header">
        <button class="back-btn" @click="emit('close-subpage')">← 返回</button>
        <h2 class="subpage-title">📖 生词本</h2>
        <button class="refresh-btn" @click="loadAllVocabulary" :disabled="isLoadingVocab">
          <span :class="{ spinning: isLoadingVocab }">🔄</span>
        </button>
      </div>
      <div class="subpage-content">
        <div v-if="isLoadingVocab" class="loading-state">
          <div class="loading-spinner"></div>
          <span>加载中...</span>
        </div>
        <div v-else-if="allVocabulary.length === 0" class="empty-state">
          <div class="empty-icon">📖</div>
          <h3>还没有收藏的生词</h3>
          <p>阅读文章时点击高亮词汇，可以添加到生词本</p>
        </div>
        <div v-else class="vocabulary-grid">
          <div 
            v-for="word in allVocabulary" 
            :key="word.word"
            class="vocab-card"
          >
            <div class="vocab-card-header">
              <span class="vocab-word">{{ word.word }}</span>
              <button class="vocab-play-btn" @click="playWordTTS(word.word)">🔊</button>
            </div>
            <div class="vocab-phonetic" v-if="word.phonetic">{{ word.phonetic }}</div>
            <div class="vocab-definition">{{ word.definition }}</div>
            <div class="vocab-footer">
              <div class="vocab-mastery">
                <span 
                  v-for="level in 3" 
                  :key="level"
                  class="mastery-dot"
                  :class="{ filled: level <= (word.mastery_level || 0) }"
                  @click="updateMastery(word.word, level)"
                ></span>
              </div>
              <button class="vocab-delete-btn" @click="deleteVocabWord(word.word)">删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 主页面 -->
    <template v-else>
      <!-- 顶部状态栏 -->
      <div class="discovery-header">
        <div class="topic-status">
          <span class="status-dot" :class="{ active: isLoading, connected: isConnected }"></span>
          <span class="status-text">
            {{ statusText }}
          </span>
        </div>
        <div class="header-actions">
          <button class="action-btn" @click="refreshContent" :disabled="isLoading || !selectedTopic">
            <span :class="{ spinning: isLoading }">🔄</span>
            <span>换一篇</span>
          </button>
        </div>
      </div>

      <!-- 主内容区 -->
      <div class="discovery-content">
      <!-- 加载状态 - 带步骤进度 -->
      <div v-if="isLoading" class="loading-state">
        <div class="loading-steps">
          <div class="step" :class="{ active: currentStep >= 1, done: currentStep > 1 }">
            <span class="step-icon">{{ currentStep > 1 ? '✓' : '1' }}</span>
            <span class="step-text">检索内容</span>
        </div>
          <div class="step-line" :class="{ active: currentStep >= 2 }"></div>
          <div class="step" :class="{ active: currentStep >= 2, done: currentStep > 2 }">
            <span class="step-icon">{{ currentStep > 2 ? '✓' : '2' }}</span>
            <span class="step-text">适配难度</span>
          </div>
          <div class="step-line" :class="{ active: currentStep >= 3 }"></div>
          <div class="step" :class="{ active: currentStep >= 3 }">
            <span class="step-icon">3</span>
            <span class="step-text">生成练习</span>
          </div>
        </div>
        <p class="loading-message">{{ loadingMessage }}</p>
      </div>

      <!-- 空状态 -->
      <div v-else-if="!currentArticle" class="empty-state">
        <div class="empty-icon">📚</div>
        <h3>探索新内容</h3>
        <p>选择左侧话题分类，开始今日的英语学习之旅</p>
        <div class="empty-tips">
          <div class="tip">🎯 内容将根据您的水平自动调整难度</div>
          <div class="tip">📖 点击高亮词汇可查看释义</div>
          <div class="tip">🎤 支持朗读练习和理解测试</div>
        </div>
      </div>

      <!-- 文章内容 -->
      <div v-else class="article-container">
        <!-- 文章卡片 -->
        <div class="article-card">
          <div class="article-header">
            <span class="level-tag" :class="getLevelClass(userLevel)">
              {{ userLevel }} {{ getLevelName(userLevel) }} 版
            </span>
            <div class="article-meta">
              <button class="meta-btn" @click="showOriginal = !showOriginal">
                {{ showOriginal ? '返回简化版' : '查看原文' }}
              </button>
              <button class="meta-btn" @click="playArticle">
                <span>🔊</span>
              </button>
            </div>
          </div>

          <h2 class="article-title">{{ currentArticle.title }}</h2>

          <div class="article-body">
            <div 
              v-for="(paragraph, idx) in displayContent" 
              :key="idx"
              class="paragraph-wrapper"
            >
              <p 
                class="article-paragraph"
                v-html="highlightWords(paragraph)"
              ></p>
              <button 
                class="translate-btn" 
                @click="translateParagraph(paragraph)"
                title="翻译此段落"
              >
                🌐
              </button>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="article-actions">
            <button class="action-card" @click="startComprehensionTest" :disabled="!currentArticle.quiz">
              <span class="action-icon">❓</span>
              <span class="action-text">测试理解力</span>
            </button>
            <button class="action-card" @click="startReadingPractice">
              <span class="action-icon">🎤</span>
              <span class="action-text">朗读段落</span>
            </button>
            <button class="action-card" @click="explainDifficulties">
              <span class="action-icon">💡</span>
              <span class="action-text">解释难点</span>
            </button>
          </div>
        </div>

        <!-- 测验模态框 -->
        <div v-if="showQuiz && currentArticle.quiz" class="quiz-modal">
          <div class="quiz-card">
            <div class="quiz-header">
              <span class="quiz-icon">❓</span>
              <span>理解力测试</span>
              <button class="quiz-close" @click="showQuiz = false">×</button>
            </div>
            <div class="quiz-question">{{ currentArticle.quiz.question }}</div>
            <div class="quiz-options">
              <button 
                v-for="(option, idx) in currentArticle.quiz.options" 
                :key="idx"
                class="quiz-option"
                :class="{ 
                  selected: selectedQuizAnswer === idx,
                  correct: quizSubmitted && idx === currentArticle.quiz.answer_index,
                  wrong: quizSubmitted && selectedQuizAnswer === idx && idx !== currentArticle.quiz.answer_index
                }"
                @click="selectQuizAnswer(idx)"
                :disabled="quizSubmitted"
              >
                <span class="option-letter">{{ ['A', 'B', 'C', 'D'][idx] }}</span>
                <span class="option-text">{{ option }}</span>
              </button>
            </div>
            <div v-if="quizSubmitted" class="quiz-result">
              <div class="result-icon">{{ quizCorrect ? '🎉' : '💪' }}</div>
              <div class="result-text">{{ quizCorrect ? '回答正确！' : '再接再厉！' }}</div>
              <div class="result-explanation">{{ currentArticle.quiz.explanation }}</div>
            </div>
            <button 
              v-if="!quizSubmitted" 
              class="quiz-submit"
              :disabled="selectedQuizAnswer === null"
              @click="submitQuiz"
            >
              提交答案
            </button>
          </div>
        </div>

        <!-- AI 对话区域 -->
        <div v-if="aiMessages.length > 0" class="ai-chat-area">
          <div 
            v-for="(msg, idx) in aiMessages" 
            :key="idx"
            class="chat-bubble"
            :class="[msg.role, { loading: msg.loading }]"
          >
            <div class="bubble-avatar">{{ msg.role === 'ai' ? '🤖' : '👤' }}</div>
            <div class="bubble-content">
              <span v-if="msg.loading" class="loading-dots">{{ msg.content }}</span>
              <span v-else>{{ msg.content }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 错误提示 -->
    <Transition name="toast">
      <div v-if="errorMessage" class="error-toast">
        {{ errorMessage }}
      </div>
    </Transition>

    <!-- 底部输入区 -->
    <div class="discovery-input" v-if="currentArticle">
      <div class="input-wrapper">
        <button 
          class="voice-btn" 
          :class="{ recording: isRecording, processing: isVoiceProcessing }"
          @click="toggleVoiceInput"
          :disabled="isVoiceProcessing"
        >
          <span v-if="isVoiceProcessing">⏳</span>
          <span v-else-if="isRecording">⏹️</span>
          <span v-else>🎤</span>
        </button>
        <input 
          type="text" 
          v-model="userInput"
          :placeholder="isRecording ? '正在录音...' : '针对内容提问，或表达你的看法...'"
          @keyup.enter="sendMessage"
          :disabled="isChatLoading || isRecording"
        />
        <button class="send-btn" @click="sendMessage" :disabled="!userInput.trim() || isChatLoading || isRecording">
          {{ isChatLoading ? '发送中...' : '发送' }}
        </button>
      </div>
      <div v-if="isRecording" class="recording-indicator">
        <span class="recording-dot"></span>
        <span>正在录音，点击麦克风按钮停止...</span>
      </div>
    </div>

    <!-- 词汇弹窗 -->
    <Transition name="popup">
      <div v-if="selectedWord" class="word-popup" :style="popupPosition">
        <div class="popup-header">
          <span class="popup-word">{{ selectedWord.word }}</span>
          <button class="popup-close" @click="selectedWord = null">×</button>
        </div>
        <div class="popup-phonetic">{{ selectedWord.phonetic }}</div>
        <div class="popup-definition">{{ selectedWord.definition }}</div>
        <div class="popup-actions">
          <button class="popup-btn" @click="playWordAudio">🔊 发音</button>
          <button 
            class="popup-btn" 
            :class="{ added: vocabularyAdded[selectedWord.word] }"
            @click="addToVocabulary"
            :disabled="vocabularyAdded[selectedWord.word]"
          >
            {{ vocabularyAdded[selectedWord.word] ? '✓ 已添加' : '📚 加入生词本' }}
          </button>
        </div>
      </div>
    </Transition>

    <!-- 翻译弹窗 -->
    <Transition name="popup">
      <div v-if="showTranslation" class="translation-popup">
        <div class="popup-header">
          <span class="popup-title">📝 段落翻译</span>
          <button class="popup-close" @click="showTranslation = false">×</button>
        </div>
        <div class="translation-content">
          <div class="translation-original">
            <div class="translation-label">原文</div>
            <p>{{ translationOriginal }}</p>
          </div>
          <div class="translation-result">
            <div class="translation-label">译文</div>
            <p v-if="translationText">{{ translationText }}</p>
            <p v-else class="translation-loading">翻译中...</p>
          </div>
        </div>
      </div>
    </Transition>

    <!-- 成功提示 -->
    <Transition name="toast">
      <div v-if="successMessage" class="success-toast">
        {{ successMessage }}
      </div>
    </Transition>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useConversationStore } from '../stores/conversation'
import { useAuthStore } from '../stores/auth'

const props = defineProps({
  selectedTopic: {
    type: String,
    default: null
  },
  subpage: {
    type: String,
    default: null  // 'history' | 'vocabulary' | null
  }
})

const emit = defineEmits(['article-read', 'close-subpage'])

const conversation = useConversationStore()
const auth = useAuthStore()

// WebSocket 连接
let ws = null

// 状态
const isConnected = ref(false)
const isLoading = ref(false)
const isChatLoading = ref(false)
const currentStep = ref(0)
const loadingMessage = ref('')
const currentArticle = ref(null)
const showOriginal = ref(false)
const userInput = ref('')
const aiMessages = ref([])
const selectedWord = ref(null)
const popupPosition = ref({ top: '0px', left: '0px' })
const errorMessage = ref('')

// 测验状态
const showQuiz = ref(false)
const selectedQuizAnswer = ref(null)
const quizSubmitted = ref(false)
const quizCorrect = ref(false)

// 语音录制状态
const isRecording = ref(false)
const isVoiceProcessing = ref(false)
let audioContext = null
let mediaRecorder = null
let audioChunks = []

// 生词本状态
const vocabularyAdded = ref({})  // 记录已添加的单词

// 翻译状态
const showTranslation = ref(false)
const translationOriginal = ref('')
const translationText = ref('')

// 成功提示
const successMessage = ref('')

// 当前文章ID（用于关联数据）
const currentArticleId = ref(null)

// 子页面状态
const isLoadingHistory = ref(false)
const isLoadingVocab = ref(false)
const allArticleHistory = ref([])
const allVocabulary = ref([])

// 用户水平
const userLevel = computed(() => conversation.userProfile?.cefr_level || 'B1')

// 话题标签映射
const topicLabels = {
  tech: '科技前沿',
  health: '健康生活',
  culture: '文化艺术',
  business: '商业财经',
  travel: '旅行探索',
  food: '美食天地'
}

// 当前自定义话题
const currentCustomTopic = ref('')

// 状态文本
const statusText = computed(() => {
  if (isLoading.value) return loadingMessage.value || '正在获取内容...'
  if (!isConnected.value) return '正在连接...'
  if (!props.selectedTopic) return '请选择话题'
  
  // 处理自定义话题
  if (typeof props.selectedTopic === 'object' && props.selectedTopic.type === 'custom') {
    return `当前话题：${props.selectedTopic.topic}`
  }
  return `当前话题：${topicLabels[props.selectedTopic] || props.selectedTopic}`
})

// 显示内容（简化版或原版）
const displayContent = computed(() => {
  if (!currentArticle.value) return []
  return showOriginal.value 
    ? currentArticle.value.original_content 
    : currentArticle.value.simplified_content
})

// 高亮词汇列表
const highlightedWords = computed(() => {
  if (!currentArticle.value) return []
  return currentArticle.value.vocabulary || []
})

// ========== WebSocket 连接 ==========
function connectWebSocket() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    return
  }
  
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  const API_BASE = import.meta.env.PROD ? '/english' : ''
  
  const url = `${protocol}//${host}${API_BASE}/discovery/ws?user_id=${auth.userId || ''}`
  
  console.log('[Discovery] 连接 WebSocket:', url)
  ws = new WebSocket(url)
  
  ws.onopen = () => {
    console.log('[Discovery] WebSocket 已连接')
    isConnected.value = true
  }
  
  ws.onclose = () => {
    console.log('[Discovery] WebSocket 已断开')
    isConnected.value = false
    // 自动重连
    setTimeout(() => {
      if (!ws || ws.readyState === WebSocket.CLOSED) {
        connectWebSocket()
      }
    }, 3000)
  }
  
  ws.onerror = (e) => {
    console.error('[Discovery] WebSocket 错误:', e)
    errorMessage.value = '连接失败，正在重试...'
    setTimeout(() => { errorMessage.value = '' }, 3000)
  }
  
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      handleMessage(data)
    } catch (e) {
      console.error('[Discovery] 消息解析失败:', e)
    }
  }
}

function handleMessage(data) {
  console.log('[Discovery] 收到消息:', data.type)
  
  switch (data.type) {
    case 'connected':
      isConnected.value = true
      break
    
    case 'status':
      currentStep.value = data.step
      loadingMessage.value = data.message
      break
    
    case 'article':
      currentArticle.value = data.data
      currentArticleId.value = data.data.article_id  // 保存文章ID
      vocabularyAdded.value = {}  // 重置生词本状态
      isLoading.value = false
      currentStep.value = 0
      loadingMessage.value = ''
      emit('article-read', data.data)
      break
    
    case 'vocabulary_result':
      if (data.success) {
        vocabularyAdded.value[data.word] = true
        showSuccess('已添加到生词本')
      } else {
        errorMessage.value = data.message || '添加失败'
        setTimeout(() => { errorMessage.value = '' }, 3000)
      }
      break
    
    case 'translation':
      if (data.success) {
        translationText.value = data.translation
      } else {
        translationText.value = '翻译失败: ' + (data.message || '未知错误')
      }
      break
    
    case 'voice_transcription':
      // 更新用户的语音消息为转录文本
      const voiceMsg = aiMessages.value.findLast(m => m.role === 'user' && m.content.includes('语音消息'))
      if (voiceMsg) {
        voiceMsg.content = data.text || '（无法识别）'
      }
      isVoiceProcessing.value = false
      break
    
    case 'chat_response':
      // 替换加载中的消息
      if (aiMessages.value.length > 0 && aiMessages.value[aiMessages.value.length - 1].loading) {
        aiMessages.value[aiMessages.value.length - 1] = {
          role: 'ai',
          content: data.message
        }
      } else {
        aiMessages.value.push({
          role: 'ai',
          content: data.message
        })
      }
      isChatLoading.value = false
      isVoiceProcessing.value = false
      // 自动朗读 AI 回复
      playTTS(data.message)
      break
    
    case 'quiz_result':
      quizSubmitted.value = true
      quizCorrect.value = data.correct
      break
    
    case 'error':
      errorMessage.value = data.message
      isLoading.value = false
      isChatLoading.value = false
      setTimeout(() => { errorMessage.value = '' }, 5000)
      break
  }
}

function sendWsMessage(data) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data))
  } else {
    errorMessage.value = '连接已断开，正在重连...'
    connectWebSocket()
  }
}

// ========== 业务方法 ==========
function refreshContent() {
  if (!props.selectedTopic) return
  
  isLoading.value = true
  currentStep.value = 1
  loadingMessage.value = '正在检索最新内容...'
  aiMessages.value = []
  showQuiz.value = false
  quizSubmitted.value = false
  selectedQuizAnswer.value = null
  
  // 处理自定义话题
  if (typeof props.selectedTopic === 'object' && props.selectedTopic.type === 'custom') {
    currentCustomTopic.value = props.selectedTopic.topic
    sendWsMessage({
      type: 'get_article',
      topic: 'custom',
      custom_topic: props.selectedTopic.topic,
      cefr_level: userLevel.value
    })
  } else {
    currentCustomTopic.value = ''
    sendWsMessage({
      type: 'get_article',
      topic: props.selectedTopic,
      cefr_level: userLevel.value
    })
  }
}

function sendMessage() {
  if (!userInput.value.trim() || isChatLoading.value) return
  
  const message = userInput.value.trim()
  userInput.value = ''
  
  // 添加用户消息
  aiMessages.value.push({
    role: 'user',
    content: message
  })
  
  // 添加加载中的 AI 消息
  aiMessages.value.push({
    role: 'ai',
    content: '思考中...',
    loading: true
  })
  
  isChatLoading.value = true
  
  sendWsMessage({
    type: 'chat',
    message: message
  })
}

function startComprehensionTest() {
  if (!currentArticle.value?.quiz) return
  showQuiz.value = true
  quizSubmitted.value = false
  selectedQuizAnswer.value = null
}

function selectQuizAnswer(idx) {
  if (!quizSubmitted.value) {
    selectedQuizAnswer.value = idx
  }
}

function submitQuiz() {
  if (selectedQuizAnswer.value === null) return
  
  sendWsMessage({
    type: 'submit_quiz',
    answer_index: selectedQuizAnswer.value
  })
}

function startReadingPractice() {
  if (!currentArticle.value) return
  
  const firstParagraph = currentArticle.value.simplified_content?.[0] || ''
  aiMessages.value.push({
    role: 'ai',
    content: `请朗读以下段落：\n\n"${firstParagraph}"\n\n准备好后，点击下方的麦克风按钮开始录音。`
  })
}

function explainDifficulties() {
  if (!currentArticle.value) return
  
  aiMessages.value.push({
    role: 'ai',
    content: '正在分析文章难点...',
    loading: true
  })
  
  isChatLoading.value = true
  
  const vocabulary = currentArticle.value.vocabulary || []
  const vocabList = vocabulary.map(v => v.word).join(', ')
  
  sendWsMessage({
    type: 'chat',
    message: `请解释这篇文章中的关键词汇和难点。词汇列表：${vocabList}`
  })
}

// ========== 辅助方法 ==========
function getLevelClass(level) {
  if (!level) return 'level-a1'
  return `level-${level.toLowerCase()}`
}

function getLevelName(level) {
  const names = {
    'A1': 'Beginner',
    'A2': 'Elementary',
    'B1': 'Intermediate',
    'B2': 'Upper Intermediate',
    'C1': 'Advanced',
    'C2': 'Proficient'
  }
  return names[level?.toUpperCase()] || 'Intermediate'
}

function highlightWords(text) {
  if (!highlightedWords.value.length) return text
  
  let result = text
  highlightedWords.value.forEach(wordObj => {
    const regex = new RegExp(`\\b(${wordObj.word})\\b`, 'gi')
    result = result.replace(regex, `<span class="highlighted-word" data-word="${wordObj.word}">$1</span>`)
  })
  return result
}

// 播放文章 TTS
const isPlayingArticle = ref(false)

async function playArticle() {
  if (!currentArticle.value) return
  if (isPlayingArticle.value) {
    // 停止播放
    stopTTS()
    isPlayingArticle.value = false
    return
  }
  
  // 获取文章内容
  const content = displayContent.value.join(' ')
  if (!content) return
  
  console.log('[Discovery] 播放文章')
  isPlayingArticle.value = true
  
  await playTTS(content)
  isPlayingArticle.value = false
}

// 通用 TTS 播放函数
const ttsAudio = ref(null)

async function playTTS(text) {
  if (!text) return
  
  try {
    // 停止之前的播放
    stopTTS()
    
    const API_BASE = import.meta.env.PROD ? '/english' : ''
    
    // 限制文本长度
    const maxLength = 800
    const truncatedText = text.length > maxLength ? text.substring(0, maxLength) : text
    
    // 使用 POST 方法发送长文本
    const response = await fetch(`${API_BASE}/discovery/tts`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...auth.getAuthHeaders()
      },
      body: JSON.stringify({ text: truncatedText })
    })
    
    if (!response.ok) {
      throw new Error(`TTS 请求失败: ${response.status}`)
    }
    
    const blob = await response.blob()
    const audioUrl = URL.createObjectURL(blob)
    
    const audio = new Audio(audioUrl)
    ttsAudio.value = audio
    
    audio.onended = () => {
      URL.revokeObjectURL(audioUrl)
      ttsAudio.value = null
    }
    audio.onerror = (e) => {
      console.error('[Discovery] TTS 播放失败:', e)
      URL.revokeObjectURL(audioUrl)
      ttsAudio.value = null
    }
    
    await audio.play()
  } catch (e) {
    console.error('[Discovery] TTS 播放失败:', e)
  }
}

function stopTTS() {
  if (ttsAudio.value) {
    ttsAudio.value.pause()
    ttsAudio.value = null
  }
}

// ========== 语音输入 ==========
async function toggleVoiceInput() {
  if (isRecording.value) {
    stopVoiceRecording()
  } else {
    startVoiceRecording()
  }
}

async function startVoiceRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ 
      audio: {
        sampleRate: 16000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true
      } 
    })
    
    // 创建 AudioContext
    audioContext = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 16000
    })
    
    const source = audioContext.createMediaStreamSource(stream)
    const processor = audioContext.createScriptProcessor(4096, 1, 1)
    
    audioChunks = []
    
    processor.onaudioprocess = (e) => {
      const inputData = e.inputBuffer.getChannelData(0)
      // 复制数据（因为 buffer 会被重用）
      const chunk = new Float32Array(inputData)
      audioChunks.push(chunk)
    }
    
    source.connect(processor)
    processor.connect(audioContext.destination)
    
    // 保存引用以便停止
    mediaRecorder = { stream, source, processor }
    isRecording.value = true
    
    console.log('[Discovery] 开始录音')
    
  } catch (e) {
    console.error('[Discovery] 无法访问麦克风:', e)
    errorMessage.value = '无法访问麦克风: ' + e.message
    setTimeout(() => { errorMessage.value = '' }, 3000)
  }
}

function stopVoiceRecording() {
  if (mediaRecorder && isRecording.value) {
    isRecording.value = false
    isVoiceProcessing.value = true
    
    // 断开音频处理
    mediaRecorder.processor.disconnect()
    mediaRecorder.source.disconnect()
    mediaRecorder.stream.getTracks().forEach(track => track.stop())
    
    // 将 PCM 数据转换为 WAV 并发送
    const wavBlob = createWavBlob(audioChunks, 16000)
    sendVoiceMessage(wavBlob)
    
    // 关闭 AudioContext
    if (audioContext) {
      audioContext.close()
      audioContext = null
    }
    
    console.log('[Discovery] 停止录音，发送音频')
  }
}

// 创建 WAV 文件
function createWavBlob(audioChunks, sampleRate) {
  // 合并所有音频块
  const totalLength = audioChunks.reduce((acc, chunk) => acc + chunk.length, 0)
  const audioData = new Float32Array(totalLength)
  let offset = 0
  for (const chunk of audioChunks) {
    audioData.set(chunk, offset)
    offset += chunk.length
  }
  
  // 转换为 16-bit PCM
  const pcmData = new Int16Array(audioData.length)
  for (let i = 0; i < audioData.length; i++) {
    const s = Math.max(-1, Math.min(1, audioData[i]))
    pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
  }
  
  // 创建 WAV 文件头
  const wavHeader = createWavHeader(pcmData.length * 2, sampleRate, 1, 16)
  
  // 合并头和数据
  const wavBlob = new Blob([wavHeader, pcmData], { type: 'audio/wav' })
  return wavBlob
}

// 创建 WAV 文件头
function createWavHeader(dataLength, sampleRate, numChannels, bitsPerSample) {
  const buffer = new ArrayBuffer(44)
  const view = new DataView(buffer)
  
  // RIFF 标识
  writeString(view, 0, 'RIFF')
  view.setUint32(4, 36 + dataLength, true)
  writeString(view, 8, 'WAVE')
  
  // fmt 块
  writeString(view, 12, 'fmt ')
  view.setUint32(16, 16, true) // fmt 块大小
  view.setUint16(20, 1, true) // PCM 格式
  view.setUint16(22, numChannels, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * numChannels * bitsPerSample / 8, true) // 字节率
  view.setUint16(32, numChannels * bitsPerSample / 8, true) // 块对齐
  view.setUint16(34, bitsPerSample, true)
  
  // data 块
  writeString(view, 36, 'data')
  view.setUint32(40, dataLength, true)
  
  return buffer
}

function writeString(view, offset, string) {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i))
  }
}

// 发送语音消息
async function sendVoiceMessage(wavBlob) {
  // 添加用户消息占位
  aiMessages.value.push({
    role: 'user',
    content: '🎤 语音消息（转录中...）'
  })
  
  // 添加加载中的 AI 消息
    aiMessages.value.push({
      role: 'ai',
    content: '正在处理语音...',
    loading: true
  })
  
  isChatLoading.value = true
  
  // 将 WAV 转为 base64 并通过 WebSocket 发送
  const reader = new FileReader()
  reader.onload = () => {
    const base64Audio = reader.result.split(',')[1]
    sendWsMessage({
      type: 'voice_chat',
      audio_data: base64Audio,
      format: 'wav'
    })
  }
  reader.readAsDataURL(wavBlob)
}

// 播放单词发音 - 使用后端 OpenAI TTS
const isPlayingAudio = ref(false)
const audioElement = ref(null)

async function playWordAudio() {
  if (!selectedWord.value?.word) return
  if (isPlayingAudio.value) return
  
  const word = selectedWord.value.word
  console.log('[Discovery] 播放单词发音:', word)
  
  isPlayingAudio.value = true
  
  try {
    const API_BASE = import.meta.env.PROD ? '/english' : ''
    
    // 停止之前的播放
    if (audioElement.value) {
      audioElement.value.pause()
      audioElement.value = null
    }
    
    // 使用 POST 方法（更可靠）
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
    audioElement.value = audio
    
    audio.onended = () => {
      URL.revokeObjectURL(audioUrl)
      isPlayingAudio.value = false
    }
    audio.onerror = (e) => {
      console.error('[Discovery] 播放发音失败:', e)
      URL.revokeObjectURL(audioUrl)
      isPlayingAudio.value = false
      errorMessage.value = '播放失败'
      setTimeout(() => { errorMessage.value = '' }, 3000)
    }
    
    await audio.play()
  } catch (e) {
    console.error('[Discovery] 播放发音失败:', e)
    isPlayingAudio.value = false
    errorMessage.value = '播放失败'
    setTimeout(() => { errorMessage.value = '' }, 3000)
  }
}

function addToVocabulary() {
  if (selectedWord.value && !vocabularyAdded.value[selectedWord.value.word]) {
    sendWsMessage({
      type: 'add_vocabulary',
      word_data: {
        word: selectedWord.value.word,
        phonetic: selectedWord.value.phonetic,
        definition: selectedWord.value.definition,
        example_sentence: ''  // 可以从文章中提取
      }
    })
  }
}

// 翻译段落
function translateParagraph(paragraph) {
  showTranslation.value = true
  translationOriginal.value = paragraph
  translationText.value = ''
  
  sendWsMessage({
    type: 'translate',
    text: paragraph,
    target_lang: 'zh'
  })
}

// 显示成功提示
function showSuccess(message) {
  successMessage.value = message
  setTimeout(() => { successMessage.value = '' }, 2000)
}

function handleWordClick(event) {
  const target = event.target
  if (target.classList.contains('highlighted-word')) {
    const word = target.dataset.word
    const wordObj = highlightedWords.value.find(w => w.word.toLowerCase() === word.toLowerCase())
    if (wordObj) {
      selectedWord.value = wordObj
      const rect = target.getBoundingClientRect()
      popupPosition.value = {
        top: `${rect.bottom + 10}px`,
        left: `${rect.left}px`
      }
    }
  }
}

// ========== 生命周期 ==========
watch(() => props.selectedTopic, (newTopic) => {
  if (newTopic && isConnected.value) {
    refreshContent()
  }
})

onMounted(() => {
  console.log('[Discovery] onMounted, subpage:', props.subpage)
  connectWebSocket()
  document.addEventListener('click', handleWordClick)
  
  // 如果组件挂载时已有子页面，立即加载数据
  if (props.subpage === 'history') {
    loadAllArticleHistory()
  } else if (props.subpage === 'vocabulary') {
    loadAllVocabulary()
  }
})

onUnmounted(() => {
  if (ws) {
    ws.close()
  }
  document.removeEventListener('click', handleWordClick)
})

// ========== 加载历史文章 ==========
async function loadHistoryArticle(article) {
  console.log('[Discovery] 加载历史文章:', article.id)
  
  isLoading.value = true
  loadingMessage.value = '加载历史文章...'
  
  try {
    const API_BASE = import.meta.env.PROD ? '/english' : ''
    const response = await fetch(`${API_BASE}/discovery/articles/${article.id}?user_id=${auth.userId}`, {
      headers: auth.getAuthHeaders()
    })
    
    if (response.ok) {
      const data = await response.json()
      currentArticle.value = data.article
      currentArticleId.value = article.id
      vocabularyAdded.value = {}
      
      // 加载历史交互
      if (data.interactions && data.interactions.length > 0) {
        aiMessages.value = data.interactions.map(i => ({
          role: i.interaction_type === 'chat' ? 'user' : 'ai',
          content: i.interaction_type === 'chat' ? i.content : i.response
        }))
      } else {
        aiMessages.value = []
      }
    } else {
      throw new Error('加载文章失败')
    }
  } catch (e) {
    console.error('[Discovery] 加载历史文章失败:', e)
    errorMessage.value = '加载文章失败: ' + e.message
    setTimeout(() => { errorMessage.value = '' }, 3000)
  } finally {
    isLoading.value = false
    loadingMessage.value = ''
  }
}

// ========== 子页面方法 ==========

// 加载全部阅读历史
async function loadAllArticleHistory() {
  if (!auth.isLoggedIn) return
  
  isLoadingHistory.value = true
  try {
    const API_BASE = import.meta.env.PROD ? '/english' : ''
    const response = await fetch(`${API_BASE}/discovery/articles?user_id=${auth.userId}&limit=100`, {
      headers: auth.getAuthHeaders()
    })
    if (response.ok) {
      const data = await response.json()
      allArticleHistory.value = data.articles || []
    }
  } catch (e) {
    console.error('[Discovery] 加载阅读历史失败:', e)
    errorMessage.value = '加载失败'
    setTimeout(() => { errorMessage.value = '' }, 3000)
  } finally {
    isLoadingHistory.value = false
  }
}

// 加载全部生词
async function loadAllVocabulary() {
  console.log('[Discovery] 加载生词本, auth.isLoggedIn:', auth.isLoggedIn, 'userId:', auth.userId)
  if (!auth.isLoggedIn) return
  
  isLoadingVocab.value = true
  try {
    const API_BASE = import.meta.env.PROD ? '/english' : ''
    const url = `${API_BASE}/discovery/vocabulary?user_id=${auth.userId}&limit=500`
    console.log('[Discovery] 请求生词本:', url)
    const response = await fetch(url, {
      headers: auth.getAuthHeaders()
    })
    console.log('[Discovery] 生词本响应:', response.status)
    if (response.ok) {
      const data = await response.json()
      console.log('[Discovery] 生词本数据:', data)
      allVocabulary.value = data.vocabulary || []
    }
  } catch (e) {
    console.error('[Discovery] 加载生词本失败:', e)
    errorMessage.value = '加载失败'
    setTimeout(() => { errorMessage.value = '' }, 3000)
  } finally {
    isLoadingVocab.value = false
  }
}

// 从历史页面加载文章并关闭子页面
function loadHistoryArticleAndClose(article) {
  emit('close-subpage')
  loadHistoryArticle(article)
}

// 播放单词发音（子页面用）
async function playWordTTS(word) {
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
    console.error('[Discovery] 播放发音失败:', e)
  }
}

// 删除生词
async function deleteVocabWord(word) {
  try {
    const API_BASE = import.meta.env.PROD ? '/english' : ''
    const response = await fetch(`${API_BASE}/discovery/vocabulary/${encodeURIComponent(word)}?user_id=${auth.userId}`, {
      method: 'DELETE',
      headers: auth.getAuthHeaders()
    })
    if (response.ok) {
      allVocabulary.value = allVocabulary.value.filter(v => v.word !== word)
      showSuccess('已删除')
    }
  } catch (e) {
    console.error('[Discovery] 删除生词失败:', e)
    errorMessage.value = '删除失败'
    setTimeout(() => { errorMessage.value = '' }, 3000)
  }
}

// 更新掌握程度
async function updateMastery(word, level) {
  // TODO: 实现更新掌握程度的 API
  const vocab = allVocabulary.value.find(v => v.word === word)
  if (vocab) {
    vocab.mastery_level = level
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

// 获取话题标签
function getTopicLabel(topic) {
  const labels = {
    'tech': '科技前沿',
    'health': '健康生活',
    'culture': '文化艺术',
    'business': '商业财经',
    'travel': '旅行探索',
    'food': '美食天地',
    'custom': '自定义话题'
  }
  return labels[topic] || topic
}

// 格式化日期
function formatDate(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', { 
    year: 'numeric',
    month: 'short', 
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 监听子页面切换，加载数据
watch(() => props.subpage, (newVal) => {
  console.log('[Discovery] 子页面切换:', newVal)
  if (newVal === 'history') {
    loadAllArticleHistory()
  } else if (newVal === 'vocabulary') {
    loadAllVocabulary()
  }
}, { immediate: true })

// 暴露方法给父组件
defineExpose({
  loadHistoryArticle
})
</script>

<style scoped>
.discovery-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
}

/* 顶部状态栏 */
.discovery-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-light);
}

.topic-status {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
  transition: all 0.3s;
}

.status-dot.connected {
  background: var(--success);
}

.status-dot.active {
  animation: pulse 1.5s ease-in-out infinite;
  background: var(--warning);
}

.status-text {
  font-size: 0.9rem;
  color: var(--text-secondary);
}

.header-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover:not(:disabled) {
  background: var(--bg-primary);
  border-color: var(--primary);
  color: var(--primary);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinning {
  display: inline-block;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 主内容区 */
.discovery-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

/* 加载状态 - 步骤进度 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  gap: 32px;
}

.loading-steps {
  display: flex;
  align-items: center;
  gap: 0;
}

.step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  opacity: 0.4;
  transition: all 0.3s;
}

.step.active {
  opacity: 1;
}

.step.done {
  opacity: 1;
}

.step-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  border: 2px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-muted);
  transition: all 0.3s;
}

.step.active .step-icon {
  background: var(--secondary);
  border-color: var(--secondary);
  color: white;
}

.step.done .step-icon {
  background: var(--success);
  border-color: var(--success);
  color: white;
}

.step-text {
  font-size: 0.8rem;
  color: var(--text-muted);
}

.step.active .step-text {
  color: var(--text-primary);
  font-weight: 500;
}

.step-line {
  width: 60px;
  height: 2px;
  background: var(--border);
  margin: 0 8px;
  margin-bottom: 24px;
  transition: all 0.3s;
}

.step-line.active {
  background: var(--secondary);
}

.loading-message {
  color: var(--text-secondary);
  font-size: 0.95rem;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  color: var(--text-muted);
}

.empty-icon {
  font-size: 4rem;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-state h3 {
  font-size: 1.3rem;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.empty-state p {
  margin-bottom: 24px;
}

.empty-tips {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty-tips .tip {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

/* 文章容器 */
.article-container {
  max-width: 800px;
  margin: 0 auto;
}

/* 文章卡片 */
.article-card {
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-md);
  overflow: hidden;
  margin-bottom: 24px;
}

.article-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-light);
}

.level-tag {
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.level-tag.level-a1 { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.level-tag.level-a2 { background: rgba(246, 173, 85, 0.15); color: #f6ad55; }
.level-tag.level-b1 { background: rgba(99, 179, 237, 0.15); color: #63b3ed; }
.level-tag.level-b2 { background: rgba(56, 189, 248, 0.15); color: #38bdf8; }
.level-tag.level-c1 { background: rgba(72, 187, 120, 0.15); color: #48bb78; }
.level-tag.level-c2 { background: rgba(168, 85, 247, 0.15); color: #a855f7; }

.article-meta {
  display: flex;
  gap: 8px;
}

.meta-btn {
  padding: 6px 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s;
}

.meta-btn:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.article-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
  padding: 20px 24px 0;
  margin: 0;
}

.article-body {
  padding: 16px 24px 24px;
}

.article-paragraph {
  font-size: 1.1rem;
  line-height: 1.8;
  color: var(--text-primary);
  margin-bottom: 16px;
}

.article-paragraph:last-child {
  margin-bottom: 0;
}

/* 高亮词汇 */
:deep(.highlighted-word) {
  background: linear-gradient(135deg, rgba(255, 230, 109, 0.3), rgba(255, 230, 109, 0.5));
  border-bottom: 2px solid var(--accent-dark);
  padding: 0 2px;
  cursor: pointer;
  transition: all 0.2s;
  border-radius: 2px;
}

:deep(.highlighted-word:hover) {
  background: rgba(255, 230, 109, 0.6);
}

/* 操作按钮 */
.article-actions {
  display: flex;
  gap: 12px;
  padding: 16px 24px;
  background: var(--bg-tertiary);
  border-top: 1px solid var(--border-light);
}

.action-card {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s;
}

.action-card:hover:not(:disabled) {
  border-color: var(--secondary);
  background: rgba(78, 205, 196, 0.05);
}

.action-card:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-icon {
  font-size: 1.2rem;
}

.action-text {
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text-primary);
}

/* 测验模态框 */
.quiz-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.quiz-card {
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
  width: 90%;
  max-width: 500px;
  padding: 24px;
  box-shadow: var(--shadow-xl);
}

.quiz-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 20px;
}

.quiz-icon {
  font-size: 1.3rem;
}

.quiz-close {
  margin-left: auto;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  border: none;
  font-size: 1.2rem;
  cursor: pointer;
  color: var(--text-muted);
}

.quiz-question {
  font-size: 1rem;
  color: var(--text-primary);
  margin-bottom: 20px;
  line-height: 1.6;
}

.quiz-options {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 20px;
}

.quiz-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-primary);
  border: 2px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.quiz-option:hover:not(:disabled) {
  border-color: var(--secondary);
}

.quiz-option.selected {
  border-color: var(--secondary);
  background: rgba(78, 205, 196, 0.1);
}

.quiz-option.correct {
  border-color: var(--success);
  background: rgba(72, 187, 120, 0.1);
}

.quiz-option.wrong {
  border-color: var(--error);
  background: rgba(239, 68, 68, 0.1);
}

.option-letter {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 0.85rem;
  flex-shrink: 0;
}

.option-text {
  font-size: 0.95rem;
  color: var(--text-primary);
}

.quiz-result {
  text-align: center;
  padding: 16px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
}

.result-icon {
  font-size: 2rem;
  margin-bottom: 8px;
}

.result-text {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.result-explanation {
  font-size: 0.9rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.quiz-submit {
  width: 100%;
  padding: 14px;
  background: linear-gradient(135deg, var(--secondary), var(--secondary-dark));
  border: none;
  border-radius: var(--radius-md);
  color: white;
  font-weight: 600;
  font-size: 1rem;
  cursor: pointer;
  transition: all 0.2s;
}

.quiz-submit:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(78, 205, 196, 0.3);
}

.quiz-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* AI 对话区域 */
.ai-chat-area {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 24px;
}

.chat-bubble {
  display: flex;
  gap: 12px;
  max-width: 85%;
}

.chat-bubble.user {
  flex-direction: row-reverse;
  margin-left: auto;
}

.bubble-avatar {
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

.chat-bubble.user .bubble-avatar {
  background: var(--primary-light);
}

.bubble-content {
  padding: 12px 16px;
  border-radius: var(--radius-lg);
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  line-height: 1.6;
  white-space: pre-wrap;
}

.chat-bubble.user .bubble-content {
  background: linear-gradient(135deg, var(--secondary), var(--secondary-dark));
  color: white;
  border: none;
}

.chat-bubble.loading .bubble-content {
  color: var(--text-muted);
  font-style: italic;
}

/* 底部输入区 */
.discovery-input {
  padding: 16px 24px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-light);
}

.input-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
  max-width: 800px;
  margin: 0 auto;
  padding: 8px 8px 8px 16px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-xl);
}

.voice-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: transparent;
  border: none;
  font-size: 1.2rem;
  cursor: pointer;
  transition: all 0.2s;
}

.voice-btn:hover:not(:disabled) {
  background: var(--bg-secondary);
}

.voice-btn.recording {
  background: rgba(239, 68, 68, 0.2);
  animation: pulse-recording 1.5s ease-in-out infinite;
}

.voice-btn.processing {
  opacity: 0.6;
  cursor: not-allowed;
}

@keyframes pulse-recording {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.1); }
}

/* 录音指示器 */
.recording-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 0.85rem;
  color: #ef4444;
}

.recording-dot {
  width: 8px;
  height: 8px;
  background: #ef4444;
  border-radius: 50%;
  animation: blink 1s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.input-wrapper input {
  flex: 1;
  padding: 10px 0;
  background: transparent;
  border: none;
  font-size: 0.95rem;
  color: var(--text-primary);
  outline: none;
}

.input-wrapper input::placeholder {
  color: var(--text-muted);
}

.send-btn {
  padding: 10px 20px;
  background: linear-gradient(135deg, var(--secondary), var(--secondary-dark));
  border: none;
  border-radius: var(--radius-md);
  color: white;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(78, 205, 196, 0.3);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 词汇弹窗 */
.word-popup {
  position: fixed;
  z-index: 1000;
  background: var(--bg-secondary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xl);
  padding: 16px;
  min-width: 280px;
  border: 1px solid var(--border);
}

.popup-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.popup-word {
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--text-primary);
}

.popup-close {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  border: none;
  font-size: 1rem;
  cursor: pointer;
  color: var(--text-muted);
}

.popup-phonetic {
  font-size: 0.9rem;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.popup-definition {
  font-size: 0.95rem;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-bottom: 12px;
}

.popup-actions {
  display: flex;
  gap: 8px;
}

.popup-btn {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s;
}

.popup-btn:hover:not(:disabled) {
  border-color: var(--primary);
  color: var(--primary);
}

.popup-btn.added {
  background: rgba(72, 187, 120, 0.1);
  border-color: var(--success);
  color: var(--success);
}

.popup-btn:disabled {
  cursor: default;
}

/* 段落翻译按钮 */
.paragraph-wrapper {
  position: relative;
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.paragraph-wrapper .article-paragraph {
  flex: 1;
}

.translate-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  font-size: 0.9rem;
  cursor: pointer;
  opacity: 0.6;
  transition: all 0.2s;
  margin-top: 4px;
}

.paragraph-wrapper:hover .translate-btn {
  opacity: 1;
}

.translate-btn:focus {
  opacity: 1;
  outline: none;
}

.translate-btn:hover {
  background: var(--secondary);
  border-color: var(--secondary);
  transform: scale(1.1);
}

/* 翻译弹窗 */
.translation-popup {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 1000;
  background: var(--bg-secondary);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xl);
  padding: 24px;
  width: 90%;
  max-width: 600px;
  max-height: 80vh;
  overflow-y: auto;
  border: 1px solid var(--border);
}

.popup-title {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.translation-content {
  margin-top: 16px;
}

.translation-original,
.translation-result {
  padding: 16px;
  border-radius: var(--radius-md);
  margin-bottom: 12px;
}

.translation-original {
  background: var(--bg-tertiary);
}

.translation-result {
  background: rgba(78, 205, 196, 0.1);
  border: 1px solid rgba(78, 205, 196, 0.2);
}

.translation-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  margin-bottom: 8px;
}

.translation-content p {
  font-size: 0.95rem;
  line-height: 1.7;
  color: var(--text-primary);
  margin: 0;
}

.translation-loading {
  color: var(--text-muted);
  font-style: italic;
}

/* 成功提示 */
.success-toast {
  position: fixed;
  bottom: 100px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--success);
  color: white;
  padding: 12px 24px;
  border-radius: var(--radius-md);
  font-size: 0.9rem;
  box-shadow: var(--shadow-lg);
  z-index: 1000;
}

/* 弹窗动画 */
.popup-enter-active,
.popup-leave-active {
  transition: all 0.2s ease;
}

.popup-enter-from,
.popup-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

/* 错误提示 */
.error-toast {
  position: fixed;
  bottom: 100px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--error);
  color: white;
  padding: 12px 24px;
  border-radius: var(--radius-md);
  font-size: 0.9rem;
  box-shadow: var(--shadow-lg);
  z-index: 1000;
}

.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(20px);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ========== 子页面样式 ========== */
.subpage-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
}

.subpage-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
}

.back-btn {
  background: none;
  border: none;
  color: var(--primary);
  font-size: 0.9rem;
  cursor: pointer;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  transition: all 0.2s;
}

.back-btn:hover {
  background: rgba(78, 205, 196, 0.1);
}

.subpage-title {
  flex: 1;
  margin: 0;
  font-size: 1.2rem;
  font-weight: 600;
  color: var(--text-primary);
}

.subpage-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

/* 历史文章网格 */
.history-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.history-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.history-card:hover {
  border-color: var(--primary);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}

.history-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.history-topic {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.history-level {
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}

.history-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 12px 0;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.history-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.history-date {
  font-size: 0.75rem;
  color: var(--text-muted);
}

/* 生词本网格 */
.vocabulary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.vocab-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px;
  transition: all 0.2s;
}

.vocab-card:hover {
  border-color: var(--primary);
}

.vocab-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.vocab-word {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--primary);
}

.vocab-play-btn {
  background: none;
  border: none;
  font-size: 1.1rem;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: all 0.2s;
}

.vocab-play-btn:hover {
  background: rgba(78, 205, 196, 0.1);
}

.vocab-phonetic {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.vocab-definition {
  font-size: 0.9rem;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-bottom: 12px;
}

.vocab-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.vocab-mastery {
  display: flex;
  gap: 6px;
}

.vocab-mastery .mastery-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--border);
  cursor: pointer;
  transition: all 0.2s;
}

.vocab-mastery .mastery-dot:hover {
  transform: scale(1.2);
}

.vocab-mastery .mastery-dot.filled {
  background: var(--primary);
}

.vocab-delete-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 0.8rem;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: all 0.2s;
}

.vocab-delete-btn:hover {
  color: var(--error);
  background: rgba(239, 68, 68, 0.1);
}

/* 子页面空状态 */
.subpage-content .empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  color: var(--text-secondary);
}

.subpage-content .empty-state .empty-icon {
  font-size: 4rem;
  margin-bottom: 16px;
}

.subpage-content .empty-state h3 {
  margin: 0 0 8px 0;
  color: var(--text-primary);
}

.subpage-content .empty-state p {
  margin: 0;
  color: var(--text-muted);
}

/* 子页面加载状态 */
.subpage-content .loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: var(--text-secondary);
}
</style>
