import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useAuthStore } from './auth'

// 获取 API 基础路径（处理子路径部署）
const API_BASE = import.meta.env.PROD ? '/english' : ''

export const useConversationStore = defineStore('conversation', () => {
  // 状态
  const conversationId = ref(null)
  const messages = ref([])
  const userProfile = ref(null)
  const latestAssessment = ref(null)
  const isConnected = ref(false)
  const isRecording = ref(false)
  const isProcessing = ref(false)
  const processingMode = ref('gpt4o-pipeline') // 'gpt4o-pipeline', 'qwen-omni', 'dashscope', 'openrouter'
  const latency = ref(null)
  const isThinking = ref(false)  // 🆕 AI 正在思考（LLM 响应 > 3秒）
  const error = ref(null)
  
  // 🆕 自动对话模式状态
  const isAutoMode = ref(true)  // 是否启用自动对话模式（VAD 检测）
  const isAISpeaking = ref(false)  // AI 是否正在说话（用于暂停 VAD）
  
  // 🆕 听不清提示（解决漏检时用户不知道的问题）
  const listenHint = ref('')  // 提示文本，为空时不显示
  let listenHintTimer = null  // 自动清除定时器
  let consecutiveEmptyCount = 0  // 连续空识别次数
  
  // 评估侧边栏相关状态
  const evaluations = ref([])  // 评估结果列表（用于侧边栏显示）
  const pendingEvaluations = ref(0)  // 等待中的评估数量
  const highlightedMessageId = ref(null)  // 当前高亮的消息 ID
  
  // WebSocket
  let ws = null
  let mediaRecorder = null
  let audioChunks = []
  
  // 🆕 WebSocket 心跳保活（增强版）
  let heartbeatTimer = null
  const HEARTBEAT_INTERVAL = 10000  // 10秒发一次心跳（更频繁）
  const HEARTBEAT_TIMEOUT = 30000   // 30秒没收到 pong 认为连接断开
  let lastPongTime = 0              // 最后收到 pong 的时间
  
  // 🆕 自动重连（指数退避 + 随机 jitter）
  let reconnectAttempts = 0
  const MAX_RECONNECT_ATTEMPTS = 8  // 最多重试 8 次
  const BASE_RECONNECT_DELAY = 1000  // 基础延迟 1 秒
  const MAX_RECONNECT_DELAY = 30000  // 最大延迟 30 秒
  let isManualClose = false  // 区分主动关闭和意外断开
  let audioContext = null
  let audioWorklet = null
  
  // 🆕 异常事件记录（用于调试和监控）
  const anomalyEvents = ref([])
  const MAX_ANOMALY_EVENTS = 50
  let interviewStartTime = 0
  let lastActivityTime = 0
  const INACTIVITY_TIMEOUT = 120000  // 2分钟无活动告警
  let inactivityTimer = null
  
  // 🆕 设备变化监听
  let deviceChangeHandler = null
  
  // 消息管理
  let currentUserMessageId = null
  let currentAssistantMessageId = null
  let messageIdCounter = 0
  
  // 音频播放队列（流式TTS）
  let audioQueue = []
  let isPlayingAudio = false
  
  // 🆕 网络抖动时的本地缓冲（短时缓存，避免丢帧）
  let pendingControlMessages = []
  const MAX_PENDING_CONTROL_MESSAGES = 20
  let pendingAudioFrames = []
  const MAX_PENDING_AUDIO_FRAMES = 150  // 🔧 从 50 增到 150（约 4.5s），覆盖更长的重连窗口
  let hasPendingStart = false
  let pendingStopAudio = false
  
  // 🆕 打断竞态保护（学习自 UserGenie）
  // 打断时设置为 true，忽略后端可能还在发送的音频块
  let isInterrupting = false
  
  // 🆕 流式音频帧计数（用于调试）
  let streamingFrameCount = 0
  
  // 🆕 用户感知延迟计算（前端精确测量）
  let vadSilenceTime = 0        // VAD 检测到静默的时刻
  let firstAudioPlayTime = 0    // TTS 首块开始播放的时刻
  let latencyMeasured = false   // 当前轮次是否已测量延迟
  
  // 🆕 完整时间轴记录（12个关键时间点）
  let vadSpeechStartTime = 0    // 用户开始说话时间
  let audioPlayEndTime = 0      // AI 音频播放结束时间
  let currentRoundId = 0        // 当前轮次 ID

  // 计算属性
  const hasConversation = computed(() => !!conversationId.value)
  const cefrLevel = computed(() => userProfile.value?.cefr_level || 'A1')

  // ==================== 异常处理 ====================
  
  /**
   * 🆕 记录异常事件
   */
  function recordAnomaly(type, message, data = null) {
    const event = {
      type,
      message,
      timestamp: Date.now(),
      data
    }
    anomalyEvents.value.push(event)
    
    // 最多保留 MAX_ANOMALY_EVENTS 条
    if (anomalyEvents.value.length > MAX_ANOMALY_EVENTS) {
      anomalyEvents.value.shift()
    }
    
    console.error(`🚨 [Anomaly] ${type}: ${message}`, data || '')
    
    // 🆕 发送到后端
    sendFrontendLog('anomaly', type, message, data)
  }
  
  /**
   * 🆕 发送前端日志到后端（用于调试）
   */
  function sendFrontendLog(level, type, message, data = null) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return
    }
    try {
      ws.send(JSON.stringify({
        type: 'frontend_log',
        level,
        log_type: type,
        message,
        data,
        timestamp: Date.now()
      }))
    } catch (e) {
      // 忽略发送失败
    }
  }
  
  /**
   * 🆕 发送时间轴事件到后端（12个关键时间点）
   * 
   * 事件类型：
   * - client_speech_start: 用户开始说话
   * - client_speech_end: 用户结束说话
   * - client_audio_first: 用户端开始收到音频
   * - client_audio_end: 用户端音频播放结束
   */
  function sendTimelineEvent(eventType, timestampMs, metadata = null) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn(`[Timeline] WebSocket 未连接，无法发送事件: ${eventType}`)
      return
    }
    try {
      ws.send(JSON.stringify({
        type: 'timeline_event',
        event_type: eventType,
        timestamp_ms: timestampMs,
        round_id: currentRoundId,
        message_round_id: currentPlayingRoundId,
        metadata: metadata
      }))
      console.log(`📊 [Timeline] ${eventType} @ ${timestampMs}`)
    } catch (e) {
      console.error('[Timeline] 发送失败:', e)
    }
  }
  
  /**
   * 🆕 显示听不清提示（解决漏检时用户不知道的问题）
   */
  function showListenHint(text, durationMs = 3000) {
    // 清除之前的定时器
    if (listenHintTimer) {
      clearTimeout(listenHintTimer)
    }
    
    listenHint.value = text
    console.log(`🎤 [ListenHint] ${text}`)
    
    // 自动清除
    listenHintTimer = setTimeout(() => {
      listenHint.value = ''
      listenHintTimer = null
    }, durationMs)
  }
  
  /**
   * 🆕 清除听不清提示
   */
  function clearListenHint() {
    if (listenHintTimer) {
      clearTimeout(listenHintTimer)
      listenHintTimer = null
    }
    listenHint.value = ''
  }
  
  /**
   * 🆕 获取所有异常事件（用于调试/上报）
   */
  function getAnomalyEvents() {
    return [...anomalyEvents.value]
  }
  
  /**
   * 🆕 获取会话健康状态
   */
  function getSessionHealth() {
    const now = Date.now()
    return {
      isConnected: isConnected.value,
      duration: interviewStartTime ? now - interviewStartTime : 0,
      lastActivityAgo: lastActivityTime ? now - lastActivityTime : 0,
      reconnectAttempts,
      anomalyCount: anomalyEvents.value.length,
      recentAnomalies: anomalyEvents.value.slice(-10)
    }
  }
  
  /**
   * 🆕 更新活动时间（重置不活动计时器）
   */
  function updateActivityTime() {
    lastActivityTime = Date.now()
    
    // 重置不活动计时器
    if (inactivityTimer) {
      clearTimeout(inactivityTimer)
    }
    
    inactivityTimer = setTimeout(() => {
      const inactiveDuration = Date.now() - lastActivityTime
      recordAnomaly('INACTIVITY_WARNING', `无活动 ${Math.round(inactiveDuration / 1000)} 秒`)
      console.warn(`⚠️ [Inactivity] 无活动 ${Math.round(inactiveDuration / 1000)} 秒`)
    }, INACTIVITY_TIMEOUT)
  }

  // 加载用户画像
  async function loadUserProfile() {
    const authStore = useAuthStore()
    if (!authStore.userId) return null
    
    try {
      const response = await fetch(`${API_BASE}/users/${authStore.userId}/profile`, {
        headers: authStore.getAuthHeaders()
      })
      
      if (response.ok) {
        const data = await response.json()
        userProfile.value = data
        console.log('用户画像已加载:', data.cefr_level, data.overall_score)
        return data
      }
    } catch (e) {
      console.warn('加载用户画像失败:', e)
    }
    return null
  }

  // 开始新对话
  async function startConversation() {
    const authStore = useAuthStore()
    if (!authStore.isLoggedIn) {
      error.value = '请先登录'
      return false
    }

    try {
      // 先加载用户画像（如果还没有加载）
      if (!userProfile.value) {
        await loadUserProfile()
      }
      
      const response = await fetch(`${API_BASE}/conversations/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authStore.getAuthHeaders()
        },
        body: JSON.stringify({ user_id: authStore.userId })
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || '创建对话失败')
      }

      const data = await response.json()
      conversationId.value = data.conversation_id
      
      // 清空消息列表，准备新对话
      messages.value = []
      latestAssessment.value = null
      error.value = ''
      // 清空评估相关状态（侧边栏显示）
      evaluations.value = []
      pendingEvaluations.value = 0
      highlightedMessageId.value = null

      // 连接 WebSocket（初始问候语由 WebSocket 返回）
      await connectWebSocket()
      
      return true
    } catch (e) {
      error.value = e.message
      return false
    }
  }

  // 连接 WebSocket
  async function connectWebSocket(continueExisting = false) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      isManualClose = true  // 🆕 标记为主动关闭
      ws.close()
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const authStore = useAuthStore()
    
    // 构建基础参数（始终传递 conversation_id）
    const baseParams = `user_level=${cefrLevel.value}&user_id=${authStore.userId || ''}`
    const convParam = conversationId.value ? `&conversation_id=${conversationId.value}` : ''
    
    // 根据处理模式选择端点
    let endpoint
    switch (processingMode.value) {
      case 'qwen-omni':
        // Qwen3-Omni 使用 openrouter-audio 端点（实际调用 qwen-omni 服务）
        endpoint = `${API_BASE}/ws/openrouter-audio?${baseParams}${convParam}`
        break
      case 'realtime':
        // Qwen3-Omni Realtime API（实时语音对话）
        endpoint = `${API_BASE}/realtime/chat?${baseParams}${convParam}`
        break
      case 'dashscope':
        // DashScope Audio 使用 streaming-voice 端点
        endpoint = `${API_BASE}/ws/streaming-voice?${baseParams}${convParam}`
        break
      case 'openrouter':
        // OpenRouter GPT-4o 使用 openrouter-audio 端点
        endpoint = `${API_BASE}/ws/openrouter-audio?${baseParams}${convParam}`
        break
      case 'gpt4o-pipeline':
        // GPT-4o 三段链路 (ASR → LLM → TTS)
        endpoint = `${API_BASE}/ws/gpt4o-pipeline?${baseParams}${convParam}`
        break
      default:
        // 默认使用 qwen-omni
        endpoint = `${API_BASE}/ws/openrouter-audio?${baseParams}${convParam}`
    }

    return new Promise((resolve, reject) => {
      ws = new WebSocket(`${protocol}//${host}${endpoint}`)

      ws.onopen = () => {
        isConnected.value = true
        reconnectAttempts = 0  // 重置重连计数
        isManualClose = false
        interviewStartTime = Date.now()
        updateActivityTime()
        console.log('WebSocket 连接成功')
        
        // 启动心跳
        startHeartbeat()
        
        // 🆕 设置设备变化监听（耳机插拔）
        setupDeviceChangeListener()

        // 📶 设置网络变更监听（WiFi↔4G）
        setupNetworkChangeListener()

        // 🔧 设置页面可见性监听（手机后台暂停心跳）
        setupVisibilityListener()

        // 断线重连后如果仍在录音，先恢复 start，再 flush
        if (isRecording.value && !hasPendingStart) {
          hasPendingStart = true
          sendControlMessage({ type: 'start' })
        }
        
        // 连接恢复后，发送暂存的控制消息和音频帧
        flushPendingMessages()
        
        resolve()
      }

      ws.onclose = async (event) => {
        isConnected.value = false
        console.log(`WebSocket 连接关闭 (code: ${event.code}, reason: ${event.reason || 'N/A'})`)
        
        // 停止心跳
        stopHeartbeat()

        // 移除设备变化监听
        removeDeviceChangeListener()

        // 📶 移除网络变更监听
        removeNetworkChangeListener()

        // 🔧 移除页面可见性监听
        removeVisibilityListener()
        
        // 记录异常断开
        if (!isManualClose) {
          recordAnomaly('WEBSOCKET_CLOSED', `连接意外关闭 (code: ${event.code})`, {
            code: event.code,
            reason: event.reason,
            duration: interviewStartTime ? Date.now() - interviewStartTime : 0
          })
        }
        
        // 如果不是主动关闭，尝试自动重连（指数退避 + jitter）
        if (!isManualClose && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts++
          const expDelay = Math.min(BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttempts - 1), MAX_RECONNECT_DELAY)
          const jitter = Math.random() * expDelay * 0.3  // 30% 随机抖动
          const delay = Math.round(expDelay + jitter)
          console.log(`🔄 [WebSocket] ${(delay/1000).toFixed(1)}秒后尝试重连 (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`)
          
          setTimeout(async () => {
            try {
              await connectWebSocket(true)  // 继续现有对话
              console.log('✅ [WebSocket] 重连成功')
            } catch (e) {
              console.error('❌ [WebSocket] 重连失败:', e)
              recordAnomaly('RECONNECT_FAILED', `重连失败 (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`, e)
            }
          }, delay)
        } else if (!isManualClose) {
          recordAnomaly('CONNECTION_LOST', '连接丢失，已达最大重连次数')
          // 会话结束后重新加载用户画像
          await loadUserProfile()
        } else {
          // 主动关闭，正常加载用户画像
          await loadUserProfile()
        }
      }

      ws.onerror = (e) => {
        console.error('WebSocket 错误:', e)
        reject(e)
      }

      ws.onmessage = handleWebSocketMessage
    })
  }
  
  // 🆕 启动心跳（带超时检测）
  function startHeartbeat() {
    stopHeartbeat()  // 先清除旧的
    lastPongTime = Date.now()
    
    heartbeatTimer = setInterval(() => {
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        return
      }
      
      const now = Date.now()
      
      // 检查是否超时（30秒没收到 pong）
      if (lastPongTime && now - lastPongTime > HEARTBEAT_TIMEOUT) {
        recordAnomaly('HEARTBEAT_TIMEOUT', `${HEARTBEAT_TIMEOUT / 1000} 秒没收到心跳响应`)
        console.error(`🚨 [心跳] ${HEARTBEAT_TIMEOUT / 1000} 秒没收到 pong，强制重连`)
        
        // 强制关闭并重连
        isManualClose = false
        ws.close(4000, 'Heartbeat timeout')
        return
      }
      
      // 发送心跳
      try {
        ws.send(JSON.stringify({ type: 'ping', timestamp: now }))
        console.log('💓 [心跳] ping')
      } catch (err) {
        recordAnomaly('HEARTBEAT_SEND_FAILED', '心跳发送失败', err)
      }
    }, HEARTBEAT_INTERVAL)
    
    console.log('💓 [心跳] 已启动')
  }
  
  // 🆕 停止心跳
  function stopHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    
    // 清理不活动计时器
    if (inactivityTimer) {
      clearTimeout(inactivityTimer)
      inactivityTimer = null
    }
  }

  // 🔧 修复：页面可见性感知，手机后台时暂停心跳，避免后台节流导致误断连
  let visibilityHandler = null

  function setupVisibilityListener() {
    if (visibilityHandler) return

    visibilityHandler = () => {
      if (document.hidden) {
        // 页面进入后台：暂停心跳，避免后台 JS 节流导致超时误判
        console.log('📱 [Visibility] 页面进入后台，暂停心跳')
        if (heartbeatTimer) {
          clearInterval(heartbeatTimer)
          heartbeatTimer = null
        }
      } else {
        // 页面恢复前台：重置 pong 时间并重启心跳
        console.log('📱 [Visibility] 页面恢复前台，重启心跳')
        lastPongTime = Date.now()  // 重置，避免立即判定超时
        if (ws && ws.readyState === WebSocket.OPEN && !heartbeatTimer) {
          startHeartbeat()
        }
      }
    }

    document.addEventListener('visibilitychange', visibilityHandler)
    console.log('📱 [Visibility] 可见性监听已设置')
  }

  function removeVisibilityListener() {
    if (visibilityHandler) {
      document.removeEventListener('visibilitychange', visibilityHandler)
      visibilityHandler = null
    }
  }

  // 设备变化监听（耳机插拔检测）
  function setupDeviceChangeListener() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.ondevicechange) {
      return
    }
    
    deviceChangeHandler = async () => {
      console.log('🎧 [设备] 检测到音频设备变化')
      recordAnomaly('DEVICE_CHANGE', '音频设备发生变化（可能是耳机插拔）')
      
      // 如果正在录音，尝试重新获取媒体流
      if (isRecording.value) {
        console.log('🎧 [设备] 正在录音中，尝试恢复...')
      }
    }
    
    // 🔧 安全检查：HTTP 环境下 navigator.mediaDevices 可能不可用
    if (navigator.mediaDevices) {
      navigator.mediaDevices.addEventListener('devicechange', deviceChangeHandler)
    } else {
      console.warn('⚠️ [设备] navigator.mediaDevices 不可用（需要 HTTPS 或 localhost）')
    }
  }
  
  function removeDeviceChangeListener() {
    if (deviceChangeHandler && navigator.mediaDevices) {
      navigator.mediaDevices.removeEventListener('devicechange', deviceChangeHandler)
      deviceChangeHandler = null
    }
  }

  // ========== 网络切换检测（WiFi↔4G 自动重连）==========
  let networkChangeHandler = null

  function setupNetworkChangeListener() {
    if (networkChangeHandler || !navigator.connection) return

    networkChangeHandler = () => {
      const conn = navigator.connection
      console.log(`📶 [网络] 类型变更: ${conn.effectiveType}, downlink: ${conn.downlink}Mbps`)
      // 网络切换时，如果 WebSocket 已断开，立即尝试重连
      if (ws && ws.readyState !== WebSocket.OPEN && !isManualClose) {
        console.log('📶 [网络] 检测到网络切换，尝试重连')
        reconnectAttempts = 0  // 重置重连计数
        connectWebSocket(true).catch(e => {
          console.warn('📶 [网络] 切换后重连失败:', e)
        })
      }
    }

    navigator.connection.addEventListener('change', networkChangeHandler)
    console.log('✅ [网络] 网络变更监听已设置')
  }

  function removeNetworkChangeListener() {
    if (networkChangeHandler && navigator.connection) {
      navigator.connection.removeEventListener('change', networkChangeHandler)
      networkChangeHandler = null
    }
  }

  function sendControlMessage(message) {
    // 🆕 参考 UserGenie: start 消息时自动添加打断标记
    // 如果 AI 正在说话，标记 isInterrupt=true，让后端立即处理打断
    if (message.type === 'start' && isAISpeaking.value) {
      message.isInterrupt = true
      console.log('🛑 [Control] start 时 AI 正在说话，添加 isInterrupt=true')
    }
    
    // 🆕 上报关键控制消息
    if (message.type === 'start' || message.type === 'stop_audio') {
      sendFrontendLog('info', `control_${message.type}`, `发送 ${message.type} 控制消息`, {
        isAISpeaking: isAISpeaking.value,
        frameCount: streamingFrameCount
      })
    }
    
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message))
      return true
    }
    pendingControlMessages.push(message)
    if (pendingControlMessages.length > MAX_PENDING_CONTROL_MESSAGES) {
      pendingControlMessages.shift()
    }
    return false
  }
  
  function sendAudioFrameNow(float32Array) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return
    }
    // 🔧 修复：改用二进制发送，减少 3 倍带宽开销
    // 之前用 JSON 数组发送，每帧 ~3KB；改为 ArrayBuffer 后每帧 ~960 bytes
    const pcmData = new Int16Array(float32Array.length)
    for (let i = 0; i < float32Array.length; i++) {
      const s = Math.max(-1, Math.min(1, float32Array[i]))
      pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
    }
    ws.send(pcmData.buffer)
  }
  
  function flushPendingMessages() {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return
    }
    if (pendingControlMessages.length > 0) {
      pendingControlMessages.forEach((message) => {
        ws.send(JSON.stringify(message))
      })
      pendingControlMessages = []
    }
    if (pendingAudioFrames.length > 0) {
      pendingAudioFrames.forEach((frame) => {
        sendAudioFrameNow(frame)
      })
      pendingAudioFrames = []
    }
    if (pendingStopAudio) {
      ws.send(JSON.stringify({ type: 'stop_audio' }))
      pendingStopAudio = false
      hasPendingStart = false
    }
  }

  // 处理 WebSocket 消息
  function handleWebSocketMessage(event) {
    try {
      const data = JSON.parse(event.data)
      
      switch (data.type) {
        case 'connected':
          console.log('WebSocket 连接成功')
          // 如果服务端返回了 conversation_id，更新本地
          if (data.conversation_id) {
            conversationId.value = data.conversation_id
            console.log('对话 ID:', data.conversation_id)
          }
          // 只有新对话才创建空的 AI 消息（继续对话时跳过）
          if (!data.is_continuing) {
            currentAssistantMessageId = ++messageIdCounter
            messages.value.push({
              id: currentAssistantMessageId,
              role: 'assistant',
              content: '',
              timestamp: new Date(),
              streaming: true
            })
          } else {
            console.log('继续历史对话，跳过初始消息创建')
          }
          break
          
        case 'processing':
          console.log('处理阶段:', data.stage, 'message_round_id:', data.message_round_id)
          // 收到 processing 消息，设置处理状态并创建 AI 消息
          isProcessing.value = true
          // 🆕 清除 LLM 超时计时器（后端开始处理了）
          if (llmTimeoutTimer) { clearTimeout(llmTimeoutTimer); llmTimeoutTimer = null }
          
          // 🆕 记录当前轮次 ID，用于后续发送 assistant_played
          if (data.message_round_id) {
            currentPlayingRoundId = data.message_round_id
          }
          
          if (data.stage === 'llm' && currentAssistantMessageId === null) {
            currentAssistantMessageId = ++messageIdCounter
            messages.value.push({
              id: currentAssistantMessageId,
              role: 'assistant',
              content: '',
              timestamp: new Date(),
              streaming: true,
              messageRoundId: data.message_round_id || null  // 🆕 关联到对应的用户消息
            })
            console.log('[processing] 创建 AI 消息:', currentAssistantMessageId, 'messageRoundId:', data.message_round_id)
          }
          break
          
        case 'recording_started':
          // 后端返回 message_round_id，更新对应的用户消息
          if (data.message_round_id) {
            // 优先更新 currentUserMessageId 对应的消息（支持同一轮复用）
            let userMsg = null
            if (currentUserMessageId !== null) {
              userMsg = messages.value.find(m => m.id === currentUserMessageId)
            }
            // 🔧 fallback: 找最后一条 recording 且没有 messageRoundId 的消息
            if (!userMsg) {
              const allPendingMsgs = messages.value.filter(m => 
                m.role === 'user' && 
                m.recording && 
                !m.messageRoundId
              )
              if (allPendingMsgs.length > 0) {
                userMsg = allPendingMsgs[allPendingMsgs.length - 1]  // 取最后一条
              }
            }
            
            if (userMsg) {
              userMsg.messageRoundId = data.message_round_id
              userMsg.recording = true
              userMsg.streaming = true
              
              // 如果有累积文本，用它初始化消息内容
              if (data.has_accumulated && data.accumulated_text) {
                userMsg.content = data.accumulated_text
                userMsg.accumulatedBase = data.accumulated_text
                console.log('[AutoMode] 使用累积文本初始化:', data.accumulated_text.substring(0, 40))
              }
              
              console.log('[AutoMode] 更新 messageRoundId:', data.message_round_id, '消息ID:', userMsg.id)
            } else {
              console.warn('[AutoMode] 未找到待更新的用户消息')
            }
          }
          break
          
        case 'text_chunk':
          // 流式文字片段 - 追加到对应的 AI 消息
          // 🆕 优先根据 message_round_id 找到对应的 AI 消息（解决回复错位问题）
          let targetAssistantMsg = null
          
          if (data.message_round_id) {
            // 根据 messageRoundId 找到对应的 AI 消息
            targetAssistantMsg = messages.value.find(m => 
              m.role === 'assistant' && m.messageRoundId === data.message_round_id
            )
            
            // 如果没找到，可能 AI 消息还没创建，用 currentAssistantMessageId 并绑定 messageRoundId
            if (!targetAssistantMsg && currentAssistantMessageId !== null) {
              targetAssistantMsg = messages.value.find(m => m.id === currentAssistantMessageId)
              if (targetAssistantMsg && !targetAssistantMsg.messageRoundId) {
                targetAssistantMsg.messageRoundId = data.message_round_id
                console.log('[text_chunk] 绑定 messageRoundId:', data.message_round_id, '到消息:', currentAssistantMessageId)
              }
            }
          } else if (currentAssistantMessageId !== null) {
            // 兼容旧模式：没有 message_round_id 时使用 currentAssistantMessageId
            targetAssistantMsg = messages.value.find(m => m.id === currentAssistantMessageId)
          }
          
          if (targetAssistantMsg) {
            // 🚀 修复：只有流式状态的消息才更新，避免覆盖已结束的消息
            if (targetAssistantMsg.streaming !== false) {
              targetAssistantMsg.content += data.text
            } else {
              console.warn('[text_chunk] 消息已结束，忽略更新:', targetAssistantMsg.id, targetAssistantMsg.content?.substring(0, 30))
            }
          }
          break
          
        case 'sentence_end':
          // 一句话结束（用于调试）
          console.log('句子结束:', data.sentence?.substring(0, 30))
          break
          
        case 'transcription_chunk':
          // 流式转录 chunk - 逐步更新用户消息内容
          // 🔧 用户说 A → 停顿 → 说 C 时，只追加 C 不覆盖已显示的 A
          const isPlaceholder = (s) => !s || !s.trim() || s.includes('正在聆听') || s.includes('正在处理')
          const appendOrSet = (userMsg, text) => {
            if (userMsg.recording) userMsg.recording = false
            if (isPlaceholder(userMsg.content)) {
              userMsg.content = text
            } else {
              userMsg.content = (userMsg.content.trim() + ' ' + text).trim()
            }
          }
          if (data.message_round_id) {
            const userMsg = messages.value.find(m => m.messageRoundId === data.message_round_id)
            if (userMsg) {
              if (userMsg.streaming !== false) {
                appendOrSet(userMsg, data.text)
                userMsg.streaming = true
              } else {
                console.warn('[transcription_chunk] 消息已结束，忽略更新:', data.message_round_id, userMsg.content?.substring(0, 30))
              }
            }
          } else if (currentUserMessageId !== null) {
            const userMsg = messages.value.find(m => m.id === currentUserMessageId)
            if (userMsg) {
              if (userMsg.streaming !== false) {
                appendOrSet(userMsg, data.text)
                userMsg.streaming = true
              } else {
                console.warn('[transcription_chunk] 消息已结束，忽略更新:', currentUserMessageId, userMsg.content?.substring(0, 30))
              }
            }
          }
          break
          
        case 'transcription':
          // 完整转录结果 - 更新当前用户消息（流式完成）
          if (data.message_round_id) {
            // 🆕 严格通过 message_round_id 查找对应的用户消息
            let userMsg = messages.value.find(m => m.messageRoundId === data.message_round_id)
            
            if (!userMsg) {
              // 🔧 精确 fallback：只匹配 currentUserMessageId 对应的消息
              // 这样可以避免匹配到之前残留的脏数据
              if (currentUserMessageId !== null) {
                const currentMsg = messages.value.find(m => m.id === currentUserMessageId)
                if (currentMsg && currentMsg.role === 'user' && !currentMsg.messageRoundId) {
                  userMsg = currentMsg
                  userMsg.messageRoundId = data.message_round_id
                  console.log('[Transcription] 使用 currentUserMessageId 匹配:', currentUserMessageId)
                }
              }
            }
            
            if (!userMsg) {
              // 🔧 最后兜底：只匹配消息列表中**最后一条**符合条件的用户消息
              // 而不是第一条（避免匹配到旧的脏数据）
              const allPendingMsgs = messages.value.filter(m => 
                m.role === 'user' && 
                m.recording && 
                !m.messageRoundId
              )
              if (allPendingMsgs.length > 0) {
                userMsg = allPendingMsgs[allPendingMsgs.length - 1]  // 取最后一条
                userMsg.messageRoundId = data.message_round_id
                console.log('[Transcription] 兜底匹配最后一条 pending 消息:', userMsg.id)
              }
            }
            
            if (userMsg) {
              // 🔧 用户说 A → 停顿 → 说 C：已有 A 或 A C 时，绝不用后端只回的新段 C 覆盖，避免闪烁和丢内容
              const existing = (userMsg.content || '').trim()
              const isPlaceholderContent = !existing || existing.includes('正在聆听') || existing.includes('正在处理')
              const newText = (data.text || '').trim()
              if (!isPlaceholderContent && existing && newText) {
                if (existing.includes(newText) && existing.length > newText.length) {
                  // 后端只回了新段 C，当前已是 A C → 保留不覆盖，避免一闪而过
                  userMsg.content = existing
                  console.log('[Transcription] ✅ 保留已有内容（后端仅新段）:', userMsg.id, 'content:', existing?.substring(0, 40))
                } else if (newText.includes(existing) || newText === existing) {
                  userMsg.content = newText
                } else if (!newText.includes(existing) && !existing.includes(newText)) {
                  userMsg.content = (existing + ' ' + newText).trim()
                  console.log('[Transcription] ✅ 追加片段:', userMsg.id, '→', userMsg.content?.substring(0, 50))
                } else {
                  userMsg.content = newText
                }
              } else {
                userMsg.content = newText || userMsg.content
              }
              userMsg.recording = false
              userMsg.streaming = false

              // 🔧 若最终仍无有效内容（空转录导致空白气泡），移除该条消息，避免出现无字气泡
              const finalContent = (userMsg.content || '').trim()
              if (!finalContent || finalContent === '正在聆听...' || finalContent === '正在处理...') {
                const idx = messages.value.findIndex(m => m.id === userMsg.id)
                if (idx !== -1) {
                  messages.value.splice(idx, 1)
                  if (currentUserMessageId === userMsg.id) currentUserMessageId = null
                  if (pendingEvaluations.value > 0) pendingEvaluations.value--
                  console.log('[Transcription] 移除空转录消息，避免空白气泡:', userMsg.id)
                }
              } else {
                consecutiveEmptyCount = 0
                clearListenHint()
                console.log('[Transcription] ✅ 更新消息:', userMsg.id, 'messageRoundId:', data.message_round_id, 'text:', userMsg.content?.substring(0, 30))
              }
            } else {
              console.error('[Transcription] ❌ 未找到对应消息! message_round_id:', data.message_round_id)
              console.error('[Transcription] 当前 currentUserMessageId:', currentUserMessageId)
              console.error('[Transcription] 消息列表:', messages.value.map(m => ({
                id: m.id, 
                role: m.role, 
                messageRoundId: m.messageRoundId, 
                recording: m.recording,
                content: m.content?.substring(0, 20)
              })))
            }
          } else if (currentUserMessageId !== null) {
            const userMsg = messages.value.find(m => m.id === currentUserMessageId)
            if (userMsg) {
              const existing = (userMsg.content || '').trim()
              const isPlaceholderContent = !existing || existing.includes('正在聆听') || existing.includes('正在处理')
              const newText = (data.text || '').trim()
              if (!isPlaceholderContent && existing && newText) {
                if (existing.includes(newText) && existing.length > newText.length) {
                  userMsg.content = existing
                } else if (newText.includes(existing) || newText === existing) {
                  userMsg.content = newText
                } else if (!newText.includes(existing) && !existing.includes(newText)) {
                  userMsg.content = (existing + ' ' + newText).trim()
                } else {
                  userMsg.content = newText
                }
              } else {
                userMsg.content = newText || userMsg.content
              }
              userMsg.recording = false
              userMsg.streaming = false
              const finalContent = (userMsg.content || '').trim()
              if (!finalContent || finalContent === '正在聆听...' || finalContent === '正在处理...') {
                const idx = messages.value.findIndex(m => m.id === userMsg.id)
                if (idx !== -1) {
                  messages.value.splice(idx, 1)
                  currentUserMessageId = null
                  if (pendingEvaluations.value > 0) pendingEvaluations.value--
                  console.log('[Transcription] 移除空转录消息（currentUserMessageId），避免空白气泡:', userMsg.id)
                }
              }
            }
          }
          break

        case 'asr_delta':
          // 🆕 流式 ASR 增量结果（边说边转，实时显示）
          // data.text: 当前累积的完整文本
          // data.is_final: 是否是最终结果
          if (currentUserMessageId !== null) {
            const userMsg = messages.value.find(m => m.id === currentUserMessageId)
            if (userMsg) {
              // 🚀 修复：只有流式状态的消息才更新，避免覆盖已结束的消息
              if (userMsg.streaming !== false || data.is_first) {
                // 🆕 如果有累积基础，追加新的 ASR 结果
                const curContent = (userMsg.content || '').trim()
                const isRealContent = curContent && !curContent.includes('正在聆听') && !curContent.includes('正在处理')
                if (userMsg.accumulatedBase) {
                  userMsg.content = userMsg.accumulatedBase + ' ' + data.text
                } else if (isRealContent && data.text) {
                  // 🔧 用户说 A → 停顿 → 说 C：已有 A 时，若后端发的是新段 C 则追加，若是全文 "A C" 则直接采用
                  if (data.text.trim().includes(curContent) || data.text.trim().startsWith(curContent)) {
                    userMsg.content = data.text.trim()
                  } else {
                    userMsg.content = (curContent + ' ' + data.text).trim()
                  }
                } else {
                  userMsg.content = data.text
                }
                // 如果是最终结果，标记 streaming = false
                if (data.is_final) {
                  userMsg.streaming = false
                }
                // 日志（只在第一次和最终时打印）
                if (data.is_first) {
                  console.log(`🎵 [ASR Delta] 首次: "${data.text}"`)
                } else if (data.is_final) {
                  console.log(`✅ [ASR Delta] 最终: "${data.text}"`)
                }
              } else {
                console.warn('[asr_delta] 消息已结束，忽略更新:', currentUserMessageId, userMsg.content?.substring(0, 30))
              }
            }
          }
          break
          
        case 'utterance_end':
          // Deepgram 检测到静默 - 仅更新显示，不关闭轮次
          // 轮次关闭由 turn_closed 消息处理
          console.log('🛑 [utterance_end]', data.text?.slice(0, 50))
          
          // 更新用户消息的文本
          if (currentUserMessageId !== null) {
            const userMsg = messages.value.find(m => m.id === currentUserMessageId)
            if (userMsg && data.text) {
              // 如果有累积基础，追加；否则直接更新
              if (userMsg.accumulatedBase) {
                // 检查 data.text 是否已经包含累积基础
                if (!data.text.startsWith(userMsg.accumulatedBase)) {
                  userMsg.content = userMsg.accumulatedBase + ' ' + data.text
                } else {
                  userMsg.content = data.text
                }
              } else {
                userMsg.content = data.text
              }
            }
          }
          // 注意：不再重置 currentUserMessageId，轮次由 turn_closed 关闭
          break
          
        case 'waiting_for_more':
          // 🆕 语义不完整，等待用户继续说话
          console.log('⏳ [waiting_for_more] 等待用户继续...', data.text, `置信度=${data.confidence?.toFixed(2)}`, `延迟=${data.tts_delay}s`)
          
          // 优先通过 message_round_id 查找，其次通过 currentUserMessageId
          let waitingMsg = null
          if (data.message_round_id) {
            waitingMsg = messages.value.find(m => m.messageRoundId === data.message_round_id)
          }
          if (!waitingMsg && currentUserMessageId !== null) {
            waitingMsg = messages.value.find(m => m.id === currentUserMessageId)
          }
          
          if (waitingMsg) {
            waitingMsg.content = data.text || ''
            waitingMsg.waitingForMore = true
            waitingMsg.recording = false
            waitingMsg.streaming = false
            console.log(`✅ [waiting_for_more] 设置 waitingForMore=true, msgId=${waitingMsg.id}`)
          } else {
            console.warn('⚠️ [waiting_for_more] 未找到对应消息')
          }
          
          // 重置处理状态，允许用户继续说话
          isProcessing.value = false
          isRecording.value = false
          break
          
        case 'waiting_cancelled':
          // 🆕 后端取消等待（超时或其他原因），清除 waitingForMore 状态
          console.log('❌ [waiting_cancelled] 后端取消等待:', data.reason)
          
          // 通过 message_round_id 查找消息
          if (data.message_round_id) {
            const cancelMsg = messages.value.find(m => m.messageRoundId === data.message_round_id)
            if (cancelMsg) {
              cancelMsg.waitingForMore = false
              cancelMsg.streaming = false
              console.log(`✅ [waiting_cancelled] 清除消息 ${cancelMsg.id} 的等待状态`)
            } else {
              console.warn(`⚠️ [waiting_cancelled] 未找到 message_round_id=${data.message_round_id} 的消息`)
            }
          }
          break
          
        case 'user_continuing':
          // 🆕 用户继续说话，LLM 被打断
          console.log('🔄 [user_continuing] 用户继续说话，LLM 已打断')
          
          // 🔧 修复：只更新当前轮次的消息（通过 message_round_id 匹配）
          if (data.accumulated_text && data.message_round_id) {
            const userMsg = messages.value.find(m => m.messageRoundId === data.message_round_id)
            if (userMsg) {
              userMsg.content = data.accumulated_text
              userMsg.waitingForMore = false
              userMsg.streaming = true
              console.log(`🔄 [user_continuing] 更新消息 ${userMsg.id}: "${data.accumulated_text.substring(0, 30)}..."`)
            } else {
              console.warn(`⚠️ [user_continuing] 未找到 message_round_id=${data.message_round_id} 的消息`)
            }
          }
          break
          
        case 'translation':
          // AI 回复的中文翻译 - 关联到当前 AI 消息
          if (currentAssistantMessageId !== null) {
            const assistantMsg = messages.value.find(m => m.id === currentAssistantMessageId)
            if (assistantMsg) {
              assistantMsg.translation = data.text
            }
          }
          break
          
        case 'evaluation':
          // 评估结果 - 支持新的异步评估模式
          latestAssessment.value = data.data
          
          // 新模式：评估结果带 message_round_id 和 order，添加到侧边栏
          if (data.message_round_id) {
            // 添加到评估列表（侧边栏显示）
            const evalData = {
              ...data.data,
              messageRoundId: data.message_round_id,
              order: data.order || Date.now(),  // 用于排序
              latency: data.latency,
              timestamp: new Date()
            }
            evaluations.value.push(evalData)
            
            // 按 order 排序（说话顺序）
            evaluations.value.sort((a, b) => a.order - b.order)
            
            // 减少等待中的评估数量
            if (pendingEvaluations.value > 0) {
              pendingEvaluations.value--
            }
            
            // 同时更新对应用户消息的 messageRoundId（用于牵引线关联）
            const userMsg = messages.value.find(m => m.messageRoundId === data.message_round_id)
            if (userMsg) {
              userMsg.evaluation = data.data
            }
          } else if (currentAssistantMessageId !== null) {
            // 兼容旧模式：关联到当前 AI 消息
            const assistantMsg = messages.value.find(m => m.id === currentAssistantMessageId)
            if (assistantMsg) {
              assistantMsg.assessment = data.data
            }
          }
          break
          
        case 'evaluation_skipped':
          // 评估被跳过（超时或失败）- 静默处理，不打扰用户
          console.log('评估已跳过:', data.message_round_id, data.reason, 'order:', data.order)
          
          // 减少等待中的评估数量
          if (pendingEvaluations.value > 0) {
            pendingEvaluations.value--
          }
          
          // 更新对应用户消息的状态 - 标记为已跳过
          if (data.message_round_id) {
            const userMsg = messages.value.find(m => m.messageRoundId === data.message_round_id)
            if (userMsg) {
              userMsg.evaluationSkipped = true
            }
            
            // 从评估列表中移除该 order 的占位（如果有的话）
            // 注意：跳过的评估不会显示在侧边栏，直接无感处理
          }
          // 不显示错误提示，静默处理
          break
        
        case 'recording_cancelled':
          // 🆕 转录为空，删除空消息（VAD 误触发）
          console.log('录音取消（VAD 误触发）:', data.message_round_id, data.reason)
          
          // 🔧 修复：支持多种匹配方式
          let cancelMsgIndex = -1
          
          // 1. 优先通过 message_round_id 匹配
          if (data.message_round_id) {
            cancelMsgIndex = messages.value.findIndex(m => m.messageRoundId === data.message_round_id)
          }
          
          // 2. 如果没匹配到，尝试通过 currentUserMessageId 匹配
          if (cancelMsgIndex === -1 && currentUserMessageId !== null) {
            cancelMsgIndex = messages.value.findIndex(m => m.id === currentUserMessageId)
          }
          
          // 3. 兜底：找最后一个空的 recording 状态的用户消息
          if (cancelMsgIndex === -1) {
            for (let i = messages.value.length - 1; i >= 0; i--) {
              const m = messages.value[i]
              if (m.role === 'user' && (m.recording || !m.content || m.content === '')) {
                cancelMsgIndex = i
                break
              }
            }
          }
          
          if (cancelMsgIndex !== -1) {
            const msg = messages.value[cancelMsgIndex]
            // 只删除内容为空或只有占位文本的消息
            if (!msg.content || msg.content === '' || msg.content === '正在处理...' || msg.content === '正在聆听...') {
              messages.value.splice(cancelMsgIndex, 1)
              console.log('已删除空消息:', data.message_round_id || currentUserMessageId || 'fallback')
              
              // 🆕 显示提示，让用户知道没有听清
              consecutiveEmptyCount++
              if (consecutiveEmptyCount >= 2) {
                // 连续2次以上没听清，显示更明显的提示
                showListenHint('🎤 没听清，请靠近麦克风再说一次', 4000)
              } else {
                // 第一次，轻提示
                showListenHint('🎤 请再说一次', 2500)
              }
              
              // 减少等待中的评估数量
              if (pendingEvaluations.value > 0) {
                pendingEvaluations.value--
              }
              
              // 重置 currentUserMessageId
              if (currentUserMessageId !== null && messages.value.findIndex(m => m.id === currentUserMessageId) === -1) {
                currentUserMessageId = null
              }
            }
          }
          
          // 🔧 修复：重置处理状态，允许用户继续说话
          isProcessing.value = false
          isRecording.value = false
          break
          
        case 'evaluation_error':
          // 评估失败/超时处理（兼容旧版本）
          console.warn('评估失败:', data.error, data.message)
          
          // 减少等待中的评估数量
          if (pendingEvaluations.value > 0) {
            pendingEvaluations.value--
          }
          
          // 更新对应用户消息的状态
          if (data.message_round_id) {
            const userMsg = messages.value.find(m => m.messageRoundId === data.message_round_id)
            if (userMsg) {
              userMsg.evaluationSkipped = true
            }
          }
          // 不显示错误提示，静默处理
          break
          
        case 'audio_chunk':
          // 🆕 学习自 UserGenie: 如果正在打断，忽略后端发来的音频块
          // 防止竞态条件：用户打断时后端可能还在发送音频
          if (isInterrupting) {
            console.log('🛑 [Audio] 忽略音频块 (isInterrupting=true)')
            break
          }
          
          // 音频块 - 加入队列
          // 🆕 标记 AI 开始说话
          if (!isAISpeaking.value) {
            setAISpeaking(true)
          }
          // 🔧 从后端获取采样率（MiniMax=32kHz, OpenAI=24kHz）
          if (data.sample_rate) {
            currentSampleRate = data.sample_rate
          }
          queueAudioChunk(data.data, 'mp3')
          break
        
        case 'audio_end':
          // 🆕 后端已发送完所有 TTS 音频
          console.log(`[WebSocket] 后端音频发送完毕 (lastAudioSource=${lastAudioSource ? 'exists' : 'null'}, nextPlayTime=${nextPlayTime.toFixed(2)}, currentTime=${playbackContext ? playbackContext.currentTime.toFixed(2) : 'N/A'})`)
          audioStreamEnded = true
          
          // 检查音频是否已经播放完毕
          if (!lastAudioSource) {
            // 没有音频片段，直接恢复 VAD
            console.log('[audio_end] 无音频片段，直接恢复 VAD')
            setTimeout(() => setAISpeaking(false), 300)
          } else if (playbackContext && playbackContext.currentTime >= nextPlayTime) {
            // 音频已经播放完毕（onended 可能已经触发但 audioStreamEnded 当时还是 false）
            console.log('[audio_end] 音频已播放完毕，立即恢复 VAD')
            onLastAudioChunkEnded()
          } else {
            // 音频还在播放，等 onended 触发
            console.log('[audio_end] 音频还在播放，等待 onended 触发')
          }
          break
        
        case 'asr_chunk':
          // 🆕 流式 ASR 转录片段；用户说 A → 停顿 → 说 C 时只追加 C 不覆盖 A
          if (currentUserMessageId !== null) {
            const userMsg = messages.value.find(m => m.id === currentUserMessageId)
            if (userMsg && userMsg.streaming !== false) {
              if (userMsg.recording) userMsg.recording = false
              const cur = (userMsg.content || '').trim()
              const isPlaceholder = !cur || cur.includes('正在聆听') || cur.includes('正在处理')
              const newText = (data.text || '').trim()
              if (!isPlaceholder && cur && newText) {
                userMsg.content = (cur + ' ' + newText).trim()
              } else {
                userMsg.content = newText || userMsg.content
              }
              userMsg.streaming = true
            } else if (userMsg) {
              console.warn('[asr_chunk] 消息已结束，忽略更新:', currentUserMessageId, userMsg.content?.substring(0, 30))
            }
          }
          break
        
        // ========== Realtime 模式专用消息 ==========
        case 'session_created':
          // Realtime 会话创建成功
          console.log('Realtime 会话创建:', data.session_id)
          break
          
        case 'speech_started':
          // VAD 检测到用户开始说话
          console.log('VAD: 检测到说话开始')
          // 创建新的用户消息
          currentUserMessageId = ++messageIdCounter
          const newUserMsg = {
            id: currentUserMessageId,
            role: 'user',
            content: '正在聆听...',
            timestamp: new Date(),
            recording: true,
            messageRoundId: `realtime_${Date.now()}`
          }
          messages.value.push(newUserMsg)
          pendingEvaluations.value++
          isRecording.value = true
          break
          
        case 'speech_stopped':
          // VAD 检测到用户停止说话
          console.log('VAD: 检测到说话结束')
          isRecording.value = false
          // 创建 AI 消息准备接收回复
          currentAssistantMessageId = ++messageIdCounter
          messages.value.push({
            id: currentAssistantMessageId,
            role: 'assistant',
            content: '',
            timestamp: new Date(),
            streaming: true
          })
          break
          
        case 'text_delta':
          // Realtime 模式的文本片段
          if (currentAssistantMessageId !== null) {
            const assistantMsg = messages.value.find(m => m.id === currentAssistantMessageId)
            if (assistantMsg) {
              assistantMsg.content += data.delta
            }
          }
          break
          
        case 'audio_delta':
          // Realtime 模式的音频片段 (PCM 24kHz)
          if (data.audio) {
            if (!isAISpeaking.value) {
              setAISpeaking(true)
            }
            queueAudioChunk(data.audio, 'pcm')
          }
          break
          
        case 'response_done':
          // Realtime 模式的响应完成
          console.log('Realtime: 响应完成')
          if (currentAssistantMessageId !== null) {
            const assistantMsg = messages.value.find(m => m.id === currentAssistantMessageId)
            if (assistantMsg) {
              assistantMsg.streaming = false
            }
          }
          isProcessing.value = false
          // Realtime 模式没有 audio_end，用 response_done 作为播放结束信号
          if (lastAudioSource) {
            audioStreamEnded = true
          } else {
            setAISpeaking(false)
          }
          break
          
        case 'response_cancelled':
          // 🚀 修复：LLM 响应被取消（用户继续说话）
          console.log('[response_cancelled] LLM 响应已取消，停止更新消息')
          if (currentAssistantMessageId !== null) {
            const assistantMsg = messages.value.find(m => m.id === currentAssistantMessageId)
            if (assistantMsg) {
              // 立即标记为结束，防止后续 text_chunk 继续更新
              assistantMsg.streaming = false
              // 如果消息内容为空，可以删除这条消息
              if (!assistantMsg.content || assistantMsg.content.trim() === '') {
                const index = messages.value.findIndex(m => m.id === currentAssistantMessageId)
                if (index !== -1) {
                  messages.value.splice(index, 1)
                  console.log('[response_cancelled] 已删除空的 AI 消息')
                }
              }
            }
          }
          // 重置状态，允许新的响应
          currentAssistantMessageId = null
          isProcessing.value = false
          break
          
        case 'ai_response_started':
          // 🆕 学习自 UserGenie: AI 开始生成回复
          // 重置打断标志，允许接收新的音频块
          console.log('🤖 [AI] AI 开始生成回复，重置 isInterrupting')
          isInterrupting = false
          // 重置当前消息 ID，确保新回复创建新消息气泡
          if (currentAssistantMessageId !== null) {
            const prevMsg = messages.value.find(m => m.id === currentAssistantMessageId)
            if (prevMsg) prevMsg.streaming = false
            currentAssistantMessageId = null
          }
          break
          
        case 'interrupted':
          // 响应被打断（用户主动触发或 Realtime 模式）
          console.log('🛑 AI 响应被打断:', data.message)
          stopAllAudio()
          setAISpeaking(false)
          isProcessing.value = false // 🔧 修复：打断后取消转圈状态
          // 🆕 打断确认后重置标志，准备下次对话
          isInterrupting = false
          break
          
        case 'interrupt':
          // 🆕 后端检测到用户开始说话，通知前端停止播放
          console.log('🛑 后端触发打断:', data.message)
          stopAllAudio()
          setAISpeaking(false)
          isProcessing.value = false // 🔧 修复：打断后取消转圈状态
          break
          
        case 'continue':
          // 🆕 用户在处理期间继续说话（False Interruption），内容会拼接
          console.log('🔄 用户继续说话，内容将拼接:', data.message)
          // 不需要停止音频，因为用户是继续说话
          isProcessing.value = false  // 重置处理状态
          break
          
        case 'pong':
          // 心跳响应 - 更新最后收到响应时间
          lastPongTime = Date.now()
          updateActivityTime()
          break
          
        case 'session_resumed':
          // 会话恢复确认
          console.log(`✅ [WebSocket] 会话恢复成功，已恢复 ${data.message_count || 0} 条历史消息`)
          updateActivityTime()
          break
        
        case 'thinking_indicator':
          // 🆕 AI 思考中（LLM 响应 > 3秒）
          console.log('⏳ [AI] 思考中...', data.message)
          isThinking.value = true
          break
        
        case 'thinking_indicator_end':
          // 🆕 AI 思考结束
          console.log('✅ [AI] 思考结束')
          isThinking.value = false
          break
        
        case 'performance_metrics':
          // 🆕 性能指标（学习自 UserGenie）
          if (data.metrics) {
            console.log('📊 [性能指标] Performance Metrics:')
            console.log(`   ├─ ASR: ${data.metrics.asr_latency_ms}ms`)
            console.log(`   ├─ LLM TTFT: ${data.metrics.llm_ttft_ms}ms`)
            console.log(`   ├─ LLM Total: ${data.metrics.llm_total_ms}ms`)
            console.log(`   ├─ TTS First: ${data.metrics.tts_first_chunk_ms}ms`)
            console.log(`   ├─ TTS Total: ${data.metrics.tts_total_ms}ms`)
            console.log(`   └─ Total Latency: ${data.metrics.total_latency_ms}ms`)
            // 存储性能指标供调试用
            latency.value = {
              ...latency.value,
              metrics: data.metrics
            }
          }
          break
          
        case 'done':
          console.log('✅ [WebSocket] 收到 done 消息, isProcessing → false')
          isProcessing.value = false
          isThinking.value = false  // 🆕 重置思考状态
          latency.value = data.latency
          // 标记流式结束，如果内容为空则删除消息
          if (currentAssistantMessageId !== null) {
            const assistantMsg = messages.value.find(m => m.id === currentAssistantMessageId)
            if (assistantMsg) {
              if (!assistantMsg.content || assistantMsg.content.trim() === '') {
                // 删除空的 AI 消息
                const idx = messages.value.findIndex(m => m.id === currentAssistantMessageId)
                if (idx !== -1) {
                  messages.value.splice(idx, 1)
                  console.log('[WebSocket] 删除空的 AI 消息')
                }
              } else {
                assistantMsg.streaming = false
              }
            }
          }
          // 🆕 VAD 恢复由 audio_end + onLastAudioChunkEnded 处理
          // 这里只做兜底：如果 5 秒后 isAISpeaking 还是 true，强制恢复（防止卡死）
          setTimeout(() => {
            if (isAISpeaking.value) {
              console.warn('⚠️ [done] 5秒兜底：强制恢复 VAD')
              setAISpeaking(false)
            }
          }, 5000)
          // 注意：不再重置 currentUserMessageId，因为评估轨是异步的
          // 评估结果会通过 message_round_id 关联
          currentAssistantMessageId = null
          // 摘要由后端自动生成并通过 WebSocket 的 summary_updated 消息通知
          break
        
        case 'turn_closed':
          // 🆕 后端确认轮次已关闭（AI 播放完毕）
          console.log('✅ [turn_closed] 轮次已关闭, round_id=', data.message_round_id)
          // 清理本轮状态，允许下一轮
          if (currentUserMessageId !== null) {
            const userMsg = messages.value.find(m => m.id === currentUserMessageId)
            if (userMsg) {
              userMsg.streaming = false
              userMsg.recording = false
              userMsg.waitingForMore = false
              userMsg.accumulatedBase = null
            }
          }
          
          // 🔧 清理所有空白的用户消息（防止 VAD 抖动产生的脏数据影响下一轮）
          const emptyUserMsgs = messages.value.filter(m => 
            m.role === 'user' && 
            (!m.content || m.content.trim() === '') &&
            m.id !== currentUserMessageId  // 不删除当前消息（可能正在更新）
          )
          if (emptyUserMsgs.length > 0) {
            console.log(`🧹 [turn_closed] 清理 ${emptyUserMsgs.length} 条空白消息`)
            emptyUserMsgs.forEach(emptyMsg => {
              const idx = messages.value.findIndex(m => m.id === emptyMsg.id)
              if (idx !== -1) {
                messages.value.splice(idx, 1)
              }
            })
          }
          
          currentUserMessageId = null
          isRecording.value = false
          break
          
        case 'error':
          console.warn('Backend error:', data.message)
          // 🆕 如果是空转录导致的错误，移除当前正在处理的空消息
          if (currentUserMessageId !== null) {
              const index = messages.value.findIndex(m => m.id === currentUserMessageId)
              if (index !== -1) {
                  // 如果内容是空的或者只是占位符，就删掉
                  const content = messages.value[index].content
                  if (!content || content === '' || content === '...' || content === '正在处理...' || content === '正在聆听...') {
                      console.log('移除空消息:', currentUserMessageId)
                      messages.value.splice(index, 1)
                      // 减少等待中的评估数量
                      if (pendingEvaluations.value > 0) {
                        pendingEvaluations.value--
                      }
                  }
              }
          }
          
          error.value = data.message
          isProcessing.value = false
          currentUserMessageId = null
          currentAssistantMessageId = null
          break
        
        // 🆕 参考 UserGenie: ASR 重连状态通知
        case 'asr_reconnecting':
          console.log('🔄 [ASR] 正在重连:', data.message, '尝试:', data.attempt)
          recordAnomaly('ASR_RECONNECTING', `ASR 重连中 (尝试 ${data.attempt})`)
          // 可以在 UI 上显示一个小提示，但不打扰用户
          break
        
        case 'asr_reconnected':
          console.log('✅ [ASR] 重连成功:', data.message)
          recordAnomaly('ASR_RECONNECTED', 'ASR 连接已恢复')
          break
          
        case 'summary_updated':
          // 摘要已更新，触发侧边栏刷新
          console.log('摘要已更新:', data.summary)
          // 触发自定义事件通知侧边栏刷新
          window.dispatchEvent(new CustomEvent('conversation-summary-updated', {
            detail: { conversationId: data.conversation_id, summary: data.summary }
          }))
          break
      }
    } catch (e) {
      console.error('解析消息失败:', e)
    }
  }

  // PCM 音频播放器 - 使用 Web Audio API
  let playbackContext = null
  let pcmBuffer = []  // 累积 PCM 数据
  let isPlaybackStarted = false
  let nextPlayTime = 0
  // 🔧 动态采样率：从后端 audio_chunk 消息中获取
  // - OpenAI TTS: 24000 Hz
  // - MiniMax TTS: 32000 Hz
  let currentSampleRate = 24000  // 默认值，会被后端覆盖
  
  // 🆕 追踪当前正在播放的轮次 ID（用于 assistant_played）
  let currentPlayingRoundId = null
  
  // 追踪后端是否已发送完所有音频，以及最后一个 PCM 片段的播放源
  let audioStreamEnded = false  // 后端已发送 audio_end
  let lastAudioSource = null    // 最后一个 PCM 片段的 BufferSource

  // 当最后一个 PCM 片段播放结束时调用
  function onLastAudioChunkEnded() {
    console.log('🔊 [Audio] 最后一个 PCM 片段播放完毕，恢复 VAD')
    
    // 🆕 记录音频播放结束时间（时间轴关键点14）
    audioPlayEndTime = Date.now()
    sendTimelineEvent('client_audio_end', audioPlayEndTime, {
      total_playback_duration_ms: firstAudioPlayTime > 0 ? audioPlayEndTime - firstAudioPlayTime : 0
    })
    
    // 🆕 发送 assistant_played 通知后端：这一轮 AI 输出已播放完毕
    if (ws && ws.readyState === WebSocket.OPEN && currentPlayingRoundId) {
      ws.send(JSON.stringify({
        type: 'assistant_played',
        message_round_id: currentPlayingRoundId
      }))
      console.log('📤 [assistant_played] 发送播放完成信号, round_id=', currentPlayingRoundId)
      currentPlayingRoundId = null
    }
    
    // 额外等 300ms 防止尾音/回声
    setTimeout(() => {
      setAISpeaking(false)
      audioStreamEnded = false
      lastAudioSource = null
    }, 300)
  }
  
  // 停止所有音频播放
  function stopAllAudio() {
    // 🆕 学习自 UserGenie: 设置打断标志，忽略后端可能还在发送的音频块
    isInterrupting = true
    console.log('🛑 [Audio] stopAllAudio: 设置 isInterrupting = true')
    
    if (playbackContext) {
      playbackContext.close()
      playbackContext = null
    }
    pcmBuffer = []
    isPlaybackStarted = false
    nextPlayTime = 0
    audioQueue.length = 0
    isPlayingAudio = false
    // 🆕 重置音频流追踪状态
    audioStreamEnded = false
    lastAudioSource = null
  }
  
  // 将音频块加入队列并播放 (PCM 格式)
  function queueAudioChunk(base64Data, format) {
    try {
      // 🆕 记录 TTS 首块播放时间（用于计算用户感知延迟）
      if (vadSilenceTime > 0 && !latencyMeasured) {
        firstAudioPlayTime = Date.now()
        const userPerceivedLatency = firstAudioPlayTime - vadSilenceTime
        latencyMeasured = true
        
        console.log(`📊 [用户感知延迟] ${userPerceivedLatency}ms (VAD静默=${vadSilenceTime}, 首块播放=${firstAudioPlayTime})`)
        
        // 🆕 上报时间轴事件：用户端开始收到音频（时间轴关键点13）
        sendTimelineEvent('client_audio_first', firstAudioPlayTime, {
          user_perceived_latency_ms: userPerceivedLatency
        })
        
        // 🆕 上报给后端记录
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            type: 'user_perceived_latency',
            latency_ms: userPerceivedLatency,
            vad_silence_time: vadSilenceTime,
            first_audio_time: firstAudioPlayTime,
            message_round_id: currentPlayingRoundId
          }))
        }
        
        // 🆕 更新 latency 状态供 UI 显示
        latency.value = {
          ...latency.value,
          user_perceived_ms: userPerceivedLatency
        }
      }
      
      // 解码 base64
      const binaryString = atob(base64Data)
      const bytes = new Uint8Array(binaryString.length)
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i)
      }
      
      // Qwen-Omni 返回的是 16-bit signed little-endian PCM
      // 转换为 Float32 用于 Web Audio API
      const int16Array = new Int16Array(bytes.buffer)
      const float32Array = new Float32Array(int16Array.length)
      for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768.0
      }
      
      // 初始化播放上下文（使用动态采样率）
      if (!playbackContext) {
        console.log(`🔊 [Audio] 初始化 AudioContext: ${currentSampleRate} Hz`)
        playbackContext = new (window.AudioContext || window.webkitAudioContext)({
          sampleRate: currentSampleRate
        })
        nextPlayTime = playbackContext.currentTime
      }
      
      // 创建音频缓冲区（使用动态采样率）
      const audioBuffer = playbackContext.createBuffer(1, float32Array.length, currentSampleRate)
      audioBuffer.getChannelData(0).set(float32Array)
      
      // 创建音频源并播放
      const source = playbackContext.createBufferSource()
      source.buffer = audioBuffer
      source.connect(playbackContext.destination)
      
      // 安排播放时间，确保连续播放
      const startTime = Math.max(playbackContext.currentTime, nextPlayTime)
      source.start(startTime)
      nextPlayTime = startTime + audioBuffer.duration
      
      // 🆕 追踪最后一个音频源，用于检测播放完毕
      lastAudioSource = source
      source.onended = () => {
        console.log(`[PCM onended] source=${source === lastAudioSource ? 'last' : 'not-last'}, audioStreamEnded=${audioStreamEnded}`)
        // 只有当这是最后一个片段，且后端已发送完所有音频时，才触发恢复 VAD
        if (audioStreamEnded && lastAudioSource === source) {
          onLastAudioChunkEnded()
        }
      }
      
      isPlayingAudio = true
    } catch (e) {
      console.error('处理音频失败:', e)
    }
  }
  
  // 播放队列中的下一个音频 (保留用于兼容性)
  function playNextInQueue() {
    // PCM 流式播放不需要队列管理
    isPlayingAudio = false
  }

  // ==================== 自动对话模式 (VAD) ====================
  
  // 🆕 用于跟踪每个录音会话的临时 ID（解决快速连续说话时的错位问题）
  let pendingRecordingId = null
  
  /**
   * 🆕 处理 VAD 帧数达到阈值时的打断（学习自 UserGenie）
   * 由 useVAD 的 onInterrupt 回调调用
   * 
   * 只有当用户说话时长 >= 0.5秒（17帧）时才触发打断
   * 这样可以过滤回声和短暂误触发
   */
  function handleVADInterrupt() {
    console.log('🛑 [AutoMode] VAD 帧数达到阈值，执行打断')
    
    // 停止所有音频播放
    stopAllAudio()
    setAISpeaking(false)
    
    // 发送打断信号到后端
    if (ws && ws.readyState === WebSocket.OPEN) {
      sendControlMessage({ type: 'interrupt' })
    }
  }
  
  /**
   * 🆕 处理 VAD 误触发（语音太短，< 30 帧 = 900ms）
   * 由 useVAD 的 onMisfire 回调调用
   * 
   * 策略：发送 stop_audio 让后端走正常流程
   * 后端会：ASR → 空结果 → 发送 recording_cancelled → 前端删除空消息
   */
  function handleVADMisfire(frameCount) {
    console.log(`⚠️ [AutoMode] VAD 误触发，帧数=${frameCount}，发送 stop_audio 触发清理`)
    
    // 发送 stop_audio 让后端走正常流程
    // 后端会对短音频做 ASR，得到空结果，发送 recording_cancelled
    // 前端收到 recording_cancelled 后会删除空消息
    if (ws && ws.readyState === WebSocket.OPEN) {
      sendControlMessage({ type: 'stop_audio' })
      console.log('📤 [AutoMode] 已发送 stop_audio 到后端（触发空消息清理）')
    }
    
    // 重置录音状态
    isRecording.value = false
    hasPendingStart = false
    pendingRecordingId = null
  }
  
  /**
   * 🆕 处理 VAD 检测到说话开始
   * 由 useVAD composable 调用
   * 
   * 🔧 修改：不再立即打断 AI，打断逻辑由 handleVADInterrupt 处理
   * 音频帧始终发送，让后端 ASR 接收
   */
  function handleVADSpeechStart() {
    const canSend = ws && ws.readyState === WebSocket.OPEN
    if (!canSend) {
      console.warn('[AutoMode] WebSocket 未连接，先暂存音频')
    }
    
    // 🆕 记录用户开始说话的精确时间（时间轴关键点1）
    vadSpeechStartTime = Date.now()
    currentRoundId++  // 新一轮对话
    
    // 🆕 上报前端日志（包含时间轴事件）
    sendFrontendLog('info', 'vad_speech_start', '用户开始说话', {
      isAISpeaking: isAISpeaking.value,
      wsConnected: canSend
    })
    
    // 🆕 上报时间轴事件：用户开始说话
    sendTimelineEvent('client_speech_start', vadSpeechStartTime)
    
    // 🔧 移除立即打断逻辑 - 打断由帧数判断触发（handleVADInterrupt）
    // 不再在 onSpeechStart 时发送 interrupt 信号
    // 音频帧会始终发送给后端 ASR，即使 AI 正在说话
    
    // 🔧 只有在 AI 不在说话时才停止音频（避免干扰正在进行的打断检测）
    if (!isAISpeaking.value) {
      stopAllAudio()
    }
    
    // 🔧 新轮次开始前，先清理之前残留的空白消息（防止错误匹配）
    const staleEmptyMsgs = messages.value.filter(m => 
      m.role === 'user' && 
      (!m.content || m.content.trim() === '') &&
      !m.recording &&  // 不在录音中
      m.id !== currentUserMessageId  // 不是当前消息
    )
    if (staleEmptyMsgs.length > 0) {
      console.log(`🧹 [AutoMode] 清理 ${staleEmptyMsgs.length} 条残留空白消息`)
      staleEmptyMsgs.forEach(msg => {
        const idx = messages.value.findIndex(m => m.id === msg.id)
        if (idx !== -1) {
          messages.value.splice(idx, 1)
        }
      })
    }
    
    // 重置帧计数
    streamingFrameCount = 0
    
    // 🔧 优先检查：如果当前已有正在录音的消息，直接复用（防止 VAD 抖动创建多条消息）
    if (currentUserMessageId !== null) {
      const currentRecordingMsg = messages.value.find(m => m.id === currentUserMessageId && m.role === 'user')
      if (currentRecordingMsg && (currentRecordingMsg.recording || currentRecordingMsg.streaming)) {
        console.log('🔄 [AutoMode] 复用当前正在录音的消息:', currentUserMessageId)
        currentRecordingMsg.recording = true
        currentRecordingMsg.streaming = true
        // 不需要再发 start，后端已经在处理
        if (!hasPendingStart) {
          hasPendingStart = true
          sendControlMessage({ type: 'start', continue_previous: true })
        }
        isRecording.value = true
        return true
      }
    }
    
    // 🆕 检查是否有等待继续的消息（waitingForMore 状态）
    const allUserMsgs = messages.value.filter(m => m.role === 'user')
    console.log(`🔍 [AutoMode] 检查 waitingForMore: 共 ${allUserMsgs.length} 条用户消息`)
    allUserMsgs.slice(-3).forEach(m => {
      console.log(`   - id=${m.id}, waitingForMore=${m.waitingForMore}, recording=${m.recording}, content="${(m.content || '').slice(0, 30)}..."`)
    })
    
    const waitingMsg = messages.value.find(m => m.role === 'user' && m.waitingForMore)
    if (waitingMsg) {
      // 复用等待中的消息，不创建新消息
      console.log('🔄 [AutoMode] 用户继续说话，复用等待中的消息:', waitingMsg.id)
      currentUserMessageId = waitingMsg.id
      waitingMsg.waitingForMore = false
      waitingMsg.recording = true
      waitingMsg.streaming = true
      pendingRecordingId = waitingMsg.pendingId || `pending_${Date.now()}`
      
      // 发送开始信号
      hasPendingStart = true
      sendControlMessage({ type: 'start' })
      isRecording.value = true
      return true
    }
    
    // 🔧 检查是否有正在录音但尚未结束的消息（VAD 抖动场景）
    const recordingMsg = messages.value.find(m => m.role === 'user' && m.recording)
    if (recordingMsg) {
      console.log('🔄 [AutoMode] 复用正在录音的消息:', recordingMsg.id)
      currentUserMessageId = recordingMsg.id
      recordingMsg.streaming = true
      pendingRecordingId = recordingMsg.pendingId || `pending_${Date.now()}`
      hasPendingStart = true
      sendControlMessage({ type: 'start', continue_previous: true })
      isRecording.value = true
      return true
    }
    
    // 🔧 兜底机制：如果上一条用户消息后没有 AI 回复，复用它
    // 这样可以避免用户说话停顿导致的消息分裂
    // 🔧 修复：当 AI 正在处理/说话时，不复用（因为即将有 AI 回复）
    const lastUserMsg = allUserMsgs.pop()
    if (lastUserMsg && !isProcessing.value && !isAISpeaking.value) {
      // 检查上一条用户消息后是否有 AI 回复
      const lastUserMsgIndex = messages.value.findIndex(m => m.id === lastUserMsg.id)
      const hasAIReplyAfter = messages.value.slice(lastUserMsgIndex + 1).some(m => m.role === 'assistant')
      
      if (!hasAIReplyAfter) {
        console.log('🔄 [AutoMode] 兜底：上条用户消息后无 AI 回复，复用:', lastUserMsg.id)
        currentUserMessageId = lastUserMsg.id
        lastUserMsg.recording = true
        lastUserMsg.streaming = true
        pendingRecordingId = lastUserMsg.pendingId || `pending_${Date.now()}`
        
        // 通知后端继续录音（会追加到之前的转录）
        hasPendingStart = true
        sendControlMessage({ type: 'start', continue_previous: true })
        isRecording.value = true
        return true
      }
    }
    
    console.log('🎙️ [AutoMode] 创建新消息（无法复用）')
    
    // 🆕 如果正在处理但 AI 还没说话，用户可以继续说话（打断处理）
    if (isProcessing.value) {
      console.log('   ↳ 打断后端处理')
    }
    
    // 🆕 生成临时录音 ID（用于匹配 recording_started 返回）
    pendingRecordingId = `pending_${Date.now()}`
    
    // 发送开始信号（后端会返回 recording_started 消息，包含正确的 message_round_id）
    hasPendingStart = true
    sendControlMessage({ type: 'start' })
    
    // 🆕 创建用户消息，使用临时 ID 作为 pendingId
    currentUserMessageId = ++messageIdCounter
    messages.value.push({
      id: currentUserMessageId,
      pendingId: pendingRecordingId,  // 🆕 临时 ID，用于匹配
      messageRoundId: null,  // 等后端返回后更新
      role: 'user',
      content: '',
      timestamp: new Date(),
      recording: true,
      streaming: true
    })
    
    // 增加等待中的评估数量
    pendingEvaluations.value++
    
    isRecording.value = true
    return true  // 成功开始，VAD 应继续发送音频
  }
  
  /**
   * 🔧 处理 VAD 检测到说话结束（静默触发）
   * 
   * 策略：延迟发送 stop_audio（2秒），给 Deepgram utterance_end 优先处理的机会
   * - 如果 Deepgram 先返回，后端会忽略后续的 stop_audio
   * - 如果 Deepgram 没响应，stop_audio 作为兜底
   */
  function handleVADSpeechEnd() {
    const canSend = ws && ws.readyState === WebSocket.OPEN
    if (!canSend) {
      console.warn('[AutoMode] WebSocket 未连接，结束信号将暂存')
    }
    
    // 🆕 记录用户停止说话的精确时刻（用于计算用户感知延迟）
    vadSilenceTime = Date.now()
    firstAudioPlayTime = 0
    latencyMeasured = false
    
    console.log(`🛑 [AutoMode] 前端 VAD 检测到静默 (${streamingFrameCount} 帧), vadSilenceTime=${vadSilenceTime}`)
    
    // 🆕 上报时间轴事件：用户结束说话（时间轴关键点2）
    sendTimelineEvent('client_speech_end', vadSilenceTime, {
      speech_duration_ms: vadSpeechStartTime > 0 ? vadSilenceTime - vadSpeechStartTime : 0,
      frame_count: streamingFrameCount
    })
    
    // 🆕 上报前端日志
    sendFrontendLog('info', 'vad_speech_end', '用户停止说话', {
      frameCount: streamingFrameCount,
      wsConnected: canSend,
      isProcessing: isProcessing.value
    })
    
    // 只更新 UI 状态
    isRecording.value = false
    
    // 更新用户消息状态
    const userMsg = messages.value.find(m => m.id === currentUserMessageId)
    if (userMsg) {
      userMsg.recording = false
      // 保持 streaming = true，等待后端转录结果
    }
    
    // 🆕 新规则：立即发送 stop_audio（作为主触发入口）
    // 后端收到后会进行语义判断，决定是否触发 LLM
    if (currentUserMessageId !== null && !isProcessing.value) {
      console.log('📤 [AutoMode] 立即发送 stop_audio')
      if (hasPendingStart || canSend) {
        if (canSend) {
          sendControlMessage({ type: 'stop_audio' })
          hasPendingStart = false
        } else {
          pendingStopAudio = true
        }
      }
      
      // 🆕 LLM 响应超时兜底：30秒没响应则恢复状态
      if (llmTimeoutTimer) clearTimeout(llmTimeoutTimer)
      llmTimeoutTimer = setTimeout(() => {
        if (isProcessing.value && !isAISpeaking.value) {
          console.error('⚠️ [超时] LLM 30秒未响应，恢复状态')
          isProcessing.value = false
          // 更新当前 AI 消息显示错误
          if (currentAssistantMessageId !== null) {
            const aiMsg = messages.value.find(m => m.id === currentAssistantMessageId)
            if (aiMsg && !aiMsg.content) {
              aiMsg.content = '抱歉，响应超时，请重试。'
              aiMsg.streaming = false
            }
          }
        }
      }, 30000)
    }
  }
  
  // LLM 响应超时计时器
  let llmTimeoutTimer = null
  
  // ==================== 双阈值系统消息 ====================
  
  /**
   * 🆕 发送预启动 STT 消息（短阈值触发：500ms）
   * 后端收到后会开始 STT，但不触发 LLM
   */
  function sendSpeculativeStt() {
    console.log('📤 [双阈值] 发送 speculative_stt')
    sendControlMessage({ type: 'speculative_stt' })
  }
  
  /**
   * 🆕 发送确认结束消息（长阈值触发：1200ms）
   * 后端收到后会使用预启动的 STT 结果调用 LLM
   */
  function sendConfirmEnd() {
    console.log('📤 [双阈值] 发送 confirm_end')
    sendControlMessage({ type: 'confirm_end' })
    
    // 设置处理中状态
    isRecording.value = false
    isProcessing.value = true
    
    // 更新用户消息状态
    const userMsg = messages.value.find(m => m.id === currentUserMessageId)
    if (userMsg) {
      userMsg.recording = false
      if (!userMsg.content) {
        userMsg.content = '正在处理...'
      }
    }
    
    // 创建 AI 消息准备接收回复
    currentAssistantMessageId = ++messageIdCounter
    messages.value.push({
      id: currentAssistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      streaming: true
    })
  }
  
  /**
   * 🆕 发送取消预启动消息（用户继续说话时触发）
   * 后端收到后会丢弃暂存的 STT 结果
   */
  function sendCancelStt() {
    console.log('📤 [双阈值] 发送 cancel_stt')
    sendControlMessage({ type: 'cancel_stt' })
  }
  
  /**
   * 🆕 发送流式音频帧
   * 由 useVAD composable 调用（每帧约 30ms）
   */
  function sendAudioFrame(float32Array) {
    // 🔧 修复：移除 isAISpeaking 限制，与 VAD 的"始终发送"设计保持一致
    // 打断场景下 VAD 会在 isAISpeaking=true 时发送帧用于打断检测，
    // 这些帧也需要到达后端 ASR，否则打断后的前几个字会丢失
    if (!isRecording.value) {
      return
    }
    
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      // 连接未就绪，暂存少量帧等待重连
      pendingAudioFrames.push(new Float32Array(float32Array))
      if (pendingAudioFrames.length > MAX_PENDING_AUDIO_FRAMES) {
        pendingAudioFrames.shift()
      }
      return
    }
    
    // 连接恢复后，优先发送暂存数据
    flushPendingMessages()
    
    // 发送音频数据（JSON 格式，便于后端区分）
    // 注意：这里不打印日志以免刷屏，但在 VAD 中有详细日志
    sendAudioFrameNow(float32Array)
    
    streamingFrameCount++
  }
  
  /**
   * 🆕 设置 AI 说话状态
   */
  function setAISpeaking(speaking) {
    isAISpeaking.value = speaking
    if (speaking) {
      console.log('🤖 [AutoMode] AI 开始说话')
      // 🔧 AI 开始回复意味着当前轮次结束，清除所有 waitingForMore 标志
      // 避免 AI 说完后用户新一轮说话被错误追加到旧消息
      messages.value.forEach(m => {
        if (m.role === 'user' && m.waitingForMore) {
          m.waitingForMore = false
          console.log(`🔄 [AutoMode] 清除 waitingForMore: msgId=${m.id}`)
        }
      })
    } else {
      console.log('🤖 [AutoMode] AI 说完')
    }
  }
  
  /**
   * 🆕 切换自动对话模式
   */
  function toggleAutoMode() {
    isAutoMode.value = !isAutoMode.value
    console.log(`[AutoMode] ${isAutoMode.value ? '启用' : '禁用'}`)
  }
  
  /**
   * 🆕 手动打断 AI 说话
   * 可由 UI 按钮或快捷键调用
   */
  function interruptAI() {
    if (!isAISpeaking.value) {
      console.log('[Interrupt] AI 未在说话')
      return false
    }
    
    console.log('🛑 [Interrupt] 用户手动打断 AI')
    
    // 发送打断信号到后端
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'interrupt' }))
    }
    
    // 本地立即停止音频
    stopAllAudio()
    setAISpeaking(false)
    
    return true
  }

  /**
   * 🆕 设置语音风格
   * @param {string} styleId - 风格 ID (friendly, professional, energetic, calm, storyteller, natural)
   */
  function setVoiceStyle(styleId) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'set_voice_style',
        style_id: styleId
      }))
      console.log(`[VoiceStyle] 发送设置请求: ${styleId}`)
    } else {
      console.warn('[VoiceStyle] WebSocket 未连接，无法设置语音风格')
    }
  }

  // 开始录音 - 使用 Web Audio API 录制 PCM 数据
  async function startRecording() {
    try {
      // 开始录音时停止所有音频播放
      stopAllAudio()
      
      // 如果 AI 正在说话，先打断
      if (isAISpeaking.value) {
        sendControlMessage({ type: 'interrupt' })
        setAISpeaking(false)
      }
      
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
      
      // Realtime 模式：持续发送音频流
      const isRealtimeMode = processingMode.value === 'realtime'
      
      processor.onaudioprocess = (e) => {
        const inputData = e.inputBuffer.getChannelData(0)
        // 复制数据（因为 buffer 会被重用）
        const chunk = new Float32Array(inputData)
        audioChunks.push(chunk)
        
        // Realtime 模式：实时发送 PCM 数据
        if (isRealtimeMode && ws && ws.readyState === WebSocket.OPEN) {
          // 转换为 16-bit PCM
          const pcmData = new Int16Array(chunk.length)
          for (let i = 0; i < chunk.length; i++) {
            const s = Math.max(-1, Math.min(1, chunk[i]))
            pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
          }
          // 发送二进制数据
          ws.send(pcmData.buffer)
        }
      }
      
      source.connect(processor)
      processor.connect(audioContext.destination)
      
      // 保存引用以便停止
      mediaRecorder = { stream, source, processor }
      isRecording.value = true
      
      // Realtime 模式不需要手动创建用户消息（由 VAD 事件触发）
      if (isRealtimeMode) {
        console.log('Realtime 模式：开始持续发送音频流')
        return
      }
      
      // 计算当前轮次（用于 message_round_id）
      const roundNumber = messages.value.filter(m => m.role === 'user').length + 1
      const messageRoundId = conversationId.value 
        ? `${conversationId.value}_${roundNumber}` 
        : `msg_${roundNumber}`
      
      // 添加用户消息（带ID和messageRoundId）
      currentUserMessageId = ++messageIdCounter
      messages.value.push({
        id: currentUserMessageId,
        messageRoundId: messageRoundId,  // 用于关联评估结果
        role: 'user',
        content: '',
        timestamp: new Date(),
        recording: true
      })
      
      // 增加等待中的评估数量
      pendingEvaluations.value++
      
    } catch (e) {
      error.value = '无法访问麦克风: ' + e.message
    }
  }
  
  // 切换录音状态（用于空格键）
  function toggleRecording() {
    if (isRecording.value) {
      stopRecording()
    } else if (!isProcessing.value) {
      startRecording()
    }
  }

  // 停止录音
  function stopRecording() {
    if (mediaRecorder && isRecording.value) {
      isRecording.value = false
      
      // 断开音频处理
      mediaRecorder.processor.disconnect()
      mediaRecorder.source.disconnect()
      mediaRecorder.stream.getTracks().forEach(track => track.stop())
      
      // Realtime 模式：停止录音后不需要发送完整音频（已实时发送）
      if (processingMode.value === 'realtime') {
        console.log('Realtime 模式：停止录音')
        // 关闭 AudioContext
        if (audioContext) {
          audioContext.close()
          audioContext = null
        }
        return
      }
      
      isProcessing.value = true
      
      // 更新占位消息
      const recordingMsg = messages.value.findLast(m => m.recording)
      if (recordingMsg) {
        recordingMsg.recording = false
        recordingMsg.content = '正在处理...'
        // 🔧 不更新 timestamp，保留开始说话的时间
      }
      
      // 将 PCM 数据转换为 WAV 并发送
      const wavBlob = createWavBlob(audioChunks, 16000)
      sendAudio(wavBlob, 'wav')
      
      // 关闭 AudioContext
      if (audioContext) {
        audioContext.close()
        audioContext = null
      }
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

  // 发送音频 - 使用二进制传输（更高效）
  async function sendAudio(audioBlob, format = 'wav') {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      error.value = 'WebSocket 未连接'
      isProcessing.value = false
      return
    }

    try {
      console.log(`发送音频: format=${format}, size=${audioBlob.size} bytes (二进制传输)`)
      
      // 1. 发送开始信号
      ws.send(JSON.stringify({ type: 'start' }))
      
      // 2. 发送音频元数据
      ws.send(JSON.stringify({
        type: 'audio_meta',
        format: format,
        size: audioBlob.size
      }))
      
      // 3. 发送二进制音频数据
      const arrayBuffer = await audioBlob.arrayBuffer()
      ws.send(arrayBuffer)
      
      // 4. 发送结束信号
      ws.send(JSON.stringify({ type: 'audio_end' }))
      
      console.log('音频发送完成，等待处理...')
      
    } catch (e) {
      error.value = '发送音频失败: ' + e.message
      console.error('发送音频失败:', e)
      isProcessing.value = false
    }
  }

  // 清空对话
  function clearConversation() {
    messages.value = []
    latestAssessment.value = null
    latency.value = null
    evaluations.value = []
    pendingEvaluations.value = 0
    highlightedMessageId.value = null
  }

  // 加载历史对话
  function loadHistoryConversation(convId, historyMessages, title) {
    // 断开当前连接
    if (ws) {
      isManualClose = true  // 🆕 标记为主动关闭
      ws.close()
      ws = null
    }
    isConnected.value = false
    
    // 设置对话 ID
    conversationId.value = convId
    
    // 清空并加载历史消息
    messages.value = []
    messageIdCounter = 0
    
    // 清空评估相关状态（侧边栏显示）
    evaluations.value = []
    pendingEvaluations.value = 0
    highlightedMessageId.value = null
    
    for (const msg of historyMessages) {
      messageIdCounter++
      const hasAssessment = msg.assessment !== null && msg.assessment !== undefined
      if (hasAssessment) {
        console.log(`消息 ${messageIdCounter} 有评估:`, msg.role, msg.assessment?.overall_score)
      }
      messages.value.push({
        id: messageIdCounter,
        role: msg.role === 'user' ? 'user' : 'assistant',
        content: msg.content,
        timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date(),
        assessment: msg.assessment || null,
        streaming: false,
        recording: false
      })
      
      // 如果有评估信息，更新最新评估
      if (msg.assessment) {
        latestAssessment.value = msg.assessment
      }
    }
    
    // 重置状态
    isProcessing.value = false
    isRecording.value = false
    error.value = null
    
    // 统计有评估的消息数
    const assessmentCount = messages.value.filter(m => m.assessment).length
    console.log(`已加载历史对话: ${convId}, ${messages.value.length} 条消息, ${assessmentCount} 条有评估`)
  }
  
  // 继续历史对话（重新连接 WebSocket）
  async function continueConversation() {
    if (!conversationId.value) {
      error.value = '没有选中的对话'
      return false
    }
    
    try {
      // 传递 true 表示继续历史对话，会携带 conversation_id
      await connectWebSocket(true)
      return true
    } catch (e) {
      error.value = '连接失败: ' + e.message
      return false
    }
  }
  
  // 生成对话摘要（后台异步执行）
  async function generateSummary(convId) {
    try {
      const response = await fetch(`${API_BASE}/conversations/generate-summary`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...useAuthStore().getAuthHeaders()
        },
        body: JSON.stringify({ conversation_id: convId })
      })
      
      if (response.ok) {
        const data = await response.json()
        console.log('摘要已生成:', data.summary)
      }
    } catch (e) {
      // 摘要生成失败不影响主流程
      console.warn('生成摘要失败:', e)
    }
  }

  // 断开连接
  function disconnect() {
    if (ws) {
      isManualClose = true  // 🆕 标记为主动关闭
      stopHeartbeat()  // 🆕 停止心跳
      ws.close()
      ws = null
    }
    isConnected.value = false
    conversationId.value = null
  }

  // 设置处理模式
  function setProcessingMode(mode) {
    processingMode.value = mode
  }
  
  // 高亮消息（用于侧边栏交互）
  function highlightMessage(messageRoundId) {
    highlightedMessageId.value = messageRoundId
  }
  
  // 取消高亮
  function unhighlightMessage() {
    highlightedMessageId.value = null
  }

  // 按需翻译 AI 回复
  async function translateMessage(messageId) {
    const msg = messages.value.find(m => m.id === messageId)
    if (!msg || msg.role !== 'assistant' || !msg.content) {
      console.warn('无法翻译：消息不存在或不是 AI 回复')
      return
    }
    
    // 如果已经有翻译，不重复翻译
    if (msg.translation) {
      console.log('已有翻译，跳过')
      return
    }
    
    // 设置翻译中状态
    msg.translating = true
    
    try {
      const response = await fetch(`${API_BASE}/api/translate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ text: msg.content })
      })
      
      if (!response.ok) {
        throw new Error('翻译请求失败')
      }
      
      const data = await response.json()
      
      if (data.translation) {
        msg.translation = data.translation
      } else if (data.error) {
        console.error('翻译失败:', data.error)
        msg.translationError = data.error
      }
    } catch (e) {
      console.error('翻译请求错误:', e)
      msg.translationError = e.message
    } finally {
      msg.translating = false
    }
  }

  return {
    // 状态
    conversationId,
    messages,
    userProfile,
    latestAssessment,
    isConnected,
    isRecording,
    isProcessing,
    processingMode,
    latency,
    isThinking,  // 🆕 AI 思考中状态
    error,
    // 🆕 自动对话模式状态
    isAutoMode,
    isAISpeaking,
    listenHint,  // 🆕 听不清提示
    // 评估侧边栏状态
    evaluations,
    pendingEvaluations,
    highlightedMessageId,
    // 计算属性
    hasConversation,
    cefrLevel,
    // 方法
    loadUserProfile,
    startConversation,
    connectWebSocket,
    startRecording,
    stopRecording,
    toggleRecording,
    clearConversation,
    disconnect,
    setProcessingMode,
    loadHistoryConversation,
    continueConversation,
    highlightMessage,
    unhighlightMessage,
    translateMessage,
    // 🆕 自动对话模式方法
    handleVADSpeechStart,
    handleVADSpeechEnd,
    handleVADInterrupt,  // 🆕 帧数打断（学习自 UserGenie）
    handleVADMisfire,    // 🆕 VAD 误触发清理
    sendAudioFrame,
    setAISpeaking,
    interruptAI,  // 🆕 手动打断 AI
    toggleAutoMode,
    stopAllAudio,
    // 🆕 双阈值系统方法
    sendSpeculativeStt,
    sendConfirmEnd,
    sendCancelStt,
    // 🆕 语音风格设置
    setVoiceStyle
  }
})
