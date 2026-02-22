/**
 * VAD (Voice Activity Detection) Composable
 * 
 * 使用 Silero VAD 在浏览器端检测用户说话状态，
 * 实现自动对话切换（无需手动按钮控制开始/结束）。
 * 
 * 🆕 架构说明：
 * - 前端 VAD 用于：检测开始说话、回声消除（AI 说话时忽略用户）、兜底结束信号
 * - 后端 Deepgram VAD（utterance_end）用于：判定用户说完、触发 LLM
 * - 前端 redemptionMs 只作为兜底，正常情况下由 Deepgram 服务端 VAD 触发
 */

import { ref, onUnmounted } from 'vue'

// VAD 配置常量
// 🆕 添加日志收集后，根据实际数据调整阈值
// P1 修复：静默 1.6s 再判定「说完了」，减少句中停顿被截断（参考 Silero 1.4s、Vivox 2s）
const VAD_CONFIG = {
  // 静音阈值（毫秒）- 前端兜底
  redemptionMs: 1600,
  
  // 最短语音段（毫秒）- 低于此值视为噪音
  // 🔧 再次降低阈值（用户反馈收音不准），支持极短词
  minSpeechMs: 200,
  
  // 语音判断阈值（0-1）- 高于此值判定为语音
  // 🔧 再次降低阈值，提高灵敏度
  positiveSpeechThreshold: 0.3,
  
  // 非语音阈值（0-1）- 低于此值判定为非语音
  // 🔧 适当降低
  negativeSpeechThreshold: 0.2,
}

// VAD 资源路径 - 使用本地文件（避免 CDN 加载失败）
const BASE_URL = import.meta.env.BASE_URL || '/'
const VAD_ASSET_BASE_URL = BASE_URL  // 本地 public 目录（包含 silero_vad_v5.onnx）
const ORT_WASM_BASE_URL = BASE_URL   // 本地 public 目录（包含 ort-wasm-*.wasm）

export function useVAD() {
  // 状态
  const isVADReady = ref(false)
  const isListening = ref(false)
  const isSpeaking = ref(false)
  const isAISpeaking = ref(false)
  const speechFrameCount = ref(0)
  const error = ref(null)
  
  // VAD 实例
  let vad = null
  let mediaStream = null
  let isRecordingSessionValid = false // 🆕 标记当前录音会话是否有效
  
  // 🆕 音频环形缓冲区（Pre-speech Buffer）
  // 用于存储检测到说话之前的音频，解决首字丢失问题
  // 🔧 从 20帧(600ms) 增加到 35帧(1050ms)，确保 "Can you" 等开头不丢失
  const PRE_BUFFER_SIZE = 35  // 35帧 ≈ 1050ms (每帧30ms)
  let audioBuffer = []        // 环形缓冲区

  // 回调函数
  let onSpeechStartCallback = null
  let onSpeechEndCallback = null
  let onAudioFrameCallback = null  // 🆕 每帧音频回调（边说边发）
  let onInterruptCallback = null   // 🆕 打断回调（用户说话达到阈值时触发）
  let onMisfireCallback = null     // 🆕 误触发回调（用于清理空消息）
  
  // 🆕 打断配置常量（学习自 UserGenie）
  const MIN_INTERRUPTION_FRAMES = 10 // 0.3s / 0.03s ≈ 10 帧
  
  /**
   * 初始化 VAD
   */
  async function initVAD() {
    if (vad) {
      console.log('[VAD] 已初始化，跳过')
      return true
    }
    
    try {
      console.log('[VAD] 开始初始化...')
      
      // 动态导入 VAD 库
      const { MicVAD } = await import('@ricky0123/vad-web')
      
      vad = await MicVAD.new({
        model: 'v5',
        baseAssetPath: VAD_ASSET_BASE_URL,
        onnxWASMBasePath: ORT_WASM_BASE_URL,
        
        // VAD 参数
        redemptionMs: VAD_CONFIG.redemptionMs,
        minSpeechMs: VAD_CONFIG.minSpeechMs,
        positiveSpeechThreshold: VAD_CONFIG.positiveSpeechThreshold,
        negativeSpeechThreshold: VAD_CONFIG.negativeSpeechThreshold,
        
        // 获取麦克风流
        getStream: async () => {
          const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
              channelCount: 1,
              sampleRate: 16000,
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
          })
          mediaStream = stream
          return stream
        },
        
        // 暂停流
        pauseStream: async (stream) => {
          stream.getTracks().forEach(track => track.stop())
        },
        
        // 恢复流
        resumeStream: async () => {
          const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
              channelCount: 1,
              sampleRate: 16000,
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
          })
          mediaStream = stream
          return stream
        },
        
        // 加载后不自动启动
        startOnLoad: false,
        
        // 🎙️ 检测到说话开始
        onSpeechStart: () => {
          // 🆕 记录触发时的概率统计
          const stats = window._vadStats || { maxProb: 0, frameCount: 0 }
          console.log(`🎙️ [VAD] 检测到说话开始 (isAISpeaking=${isAISpeaking.value}, isSpeaking=${isSpeaking.value}, 触发前maxProb=${stats.maxProb.toFixed(3)}, 总帧数=${stats.frameCount})`)
          
          isRecordingSessionValid = false // 默认无效
          
          // 🔧 Fix: 如果之前正在说话但没有正确结束，先触发结束
          if (isSpeaking.value && speechFrameCount.value > 0) {
            console.log(`⚠️ [VAD] 上一次说话未结束，先触发 onSpeechEnd (${speechFrameCount.value} 帧)`)
            if (onSpeechEndCallback) {
              onSpeechEndCallback()
            }
          }
          
          speechFrameCount.value = 0
          
          // 🆕 调用回调，让 conversation.js 处理（包括打断 AI 的逻辑）
          // 不再在这里阻止 AI 说话时的录音，而是交给上层处理
          if (onSpeechStartCallback) {
            const shouldContinue = onSpeechStartCallback()
            if (shouldContinue === false) {
              console.log('🛑 [VAD] 回调返回 false，取消录音')
              isSpeaking.value = false
              return
            }
          }
          
          isSpeaking.value = true
          isRecordingSessionValid = true // 标记有效
          
          // 🆕 发送预录音缓冲区的音频
          if (audioBuffer.length > 0 && onAudioFrameCallback) {
            console.log(`🚀 [VAD] ⚡️ 快速发送预录音缓冲: ${audioBuffer.length} 帧 (约 ${audioBuffer.length * 30}ms)`)
            let bufferedSent = 0
            for (const bufferedFrame of audioBuffer) {
              onAudioFrameCallback(bufferedFrame)
              speechFrameCount.value++
              bufferedSent++
            }
            console.log(`✅ [VAD] 预录音发送完毕，共 ${bufferedSent} 帧`)
            // 发送后不清空，保持最新状态 (虽然发送了，但不需要清空，因为后续不再使用)
          } else {
            console.log('⚠️ [VAD] 预录音缓冲区为空，可能导致首字丢失')
          }
        },
        
        // 🎤 处理每一帧音频 - 🆕 边说边发！
        onFrameProcessed: (probs, frame) => {
          // 🆕 详细日志：记录 VAD 概率分布，用于阈值调优
          // 每 50 帧（约 1.5 秒）输出一次统计
          if (!window._vadStats) {
            window._vadStats = { 
              frameCount: 0, 
              speechProbs: [], 
              maxProb: 0, 
              minProb: 1,
              aboveThreshold: 0,  // 高于阈值的帧数
              belowThreshold: 0   // 低于阈值的帧数
            }
          }
          
          const stats = window._vadStats
          stats.frameCount++
          stats.speechProbs.push(probs.isSpeech)
          stats.maxProb = Math.max(stats.maxProb, probs.isSpeech)
          stats.minProb = Math.min(stats.minProb, probs.isSpeech)
          
          if (probs.isSpeech >= VAD_CONFIG.positiveSpeechThreshold) {
            stats.aboveThreshold++
          } else {
            stats.belowThreshold++
          }
          
          // 每 50 帧输出统计
          if (stats.frameCount % 50 === 0) {
            const avgProb = stats.speechProbs.slice(-50).reduce((a, b) => a + b, 0) / 50
            console.log(`📊 [VAD Stats] 帧=${stats.frameCount}, 最近50帧: avg=${avgProb.toFixed(3)}, max=${stats.maxProb.toFixed(3)}, min=${stats.minProb.toFixed(3)}, 高于阈值=${stats.aboveThreshold}, 低于阈值=${stats.belowThreshold}, 当前阈值=${VAD_CONFIG.positiveSpeechThreshold}`)
          }
          
          // 🔧 Debug: 每 100 帧打印一次，确认 VAD 在运行
          if (Math.random() < 0.01) {
            console.log(`🔍 [VAD Debug] onFrameProcessed: prob=${probs.isSpeech.toFixed(2)}, isSpeaking=${isSpeaking.value}, isAISpeaking=${isAISpeaking.value}`)
          }
          
          // 🆕 更新预录音缓冲区 (始终保持最近 PRE_BUFFER_SIZE 帧)
          if (!isSpeaking.value) {
            // 确保存入的是副本，防止引用被修改
            audioBuffer.push(new Float32Array(frame))
            if (audioBuffer.length > PRE_BUFFER_SIZE) {
              audioBuffer.shift() // 移除最旧的帧
            }
          }
          
          // 🚀 实时流式发送音频帧（边说边发）
          // 🔧 学习自 UserGenie: 音频始终发送，不管 AI 是否在说话
          // 这是解决"打断时前几个字丢失"的关键
          if (isSpeaking.value && isRecordingSessionValid) {
            speechFrameCount.value++
            
            // 🆕 实时发送每一帧音频（即使 AI 在说话也发送）
            if (onAudioFrameCallback) {
              onAudioFrameCallback(frame)
            }
            
            // 增加日志频率：前10帧每帧都打印，之后每30帧打印
            if (speechFrameCount.value <= 10) {
               console.log(`🎤 [VAD] 发送实时帧 #${speechFrameCount.value} (prob=${probs.isSpeech.toFixed(2)}, isAISpeaking=${isAISpeaking.value})`)
            } else if (speechFrameCount.value % 30 === 0) {
              console.log(`🎤 [VAD] 已持续发送 ${speechFrameCount.value} 帧 (isAISpeaking=${isAISpeaking.value})`)
            }
            
            // 🆕 学习自 UserGenie: 基于帧数的打断逻辑
            // 每帧约 30ms，MIN_INTERRUPTION_FRAMES = 17 ≈ 0.5秒
            // 只有当用户说话时长 >= 0.5秒 且 AI 正在说话时，才触发打断
            if (isAISpeaking.value && speechFrameCount.value === MIN_INTERRUPTION_FRAMES) {
              console.log(`🛑 [VAD] 用户说话达到 ${MIN_INTERRUPTION_FRAMES} 帧 (0.5秒)，触发打断`)
              if (onInterruptCallback) {
                onInterruptCallback()
              }
              // 🔧 打断后设置 isAISpeaking = false，这样后续帧正常处理
              isAISpeaking.value = false
            }
          }
        },
        
        // 🛑 检测到说话结束（前端 VAD 兜底，正常由 Deepgram utterance_end 触发）
        onSpeechEnd: (audio) => {
          // 🆕 计算本次说话的音频时长和能量
          const durationMs = speechFrameCount.value * 30 // 每帧约 30ms
          const stats = window._vadStats || { maxProb: 0, aboveThreshold: 0 }
          console.log(`🛑 [VAD] 前端检测到静默 (帧数=${speechFrameCount.value}, 时长=${durationMs}ms, maxProb=${stats.maxProb.toFixed(3)}, 高于阈值帧=${stats.aboveThreshold}, isAISpeaking=${isAISpeaking.value})`)
          
          // 🔧 学习自 UserGenie: 回声过滤逻辑
          // 如果 AI 正在说话，说明用户说话时长没达到 MIN_INTERRUPTION_FRAMES
          // 这种情况可能是回声或误触发，忽略这次语音
          if (isAISpeaking.value) {
            console.log(`🔇 [VAD] AI 正在说话且帧数不够 (${speechFrameCount.value} < ${MIN_INTERRUPTION_FRAMES})，可能是回声，忽略`)
            isSpeaking.value = false
            speechFrameCount.value = 0
            isRecordingSessionValid = false
            return
          }
          
          // 会话无效，忽略
          if (!isRecordingSessionValid) {
            isSpeaking.value = false
            speechFrameCount.value = 0
            return
          }
          
          // 移除强制静音填充，保持原始音频流的真实性
          isSpeaking.value = false
          isRecordingSessionValid = false // 结束会话
          
          // 🆕 发送 stop_audio 作为兜底（如果 Deepgram utterance_end 未触发）
          // 正常情况下，Deepgram 服务端 VAD 会先触发，后端会忽略这个消息
          if (onSpeechEndCallback) {
            console.log(`⚠️ [VAD] 发送 stop_audio 兜底信号`)
            onSpeechEndCallback()
          }
          
          speechFrameCount.value = 0
        },
        
        // ⚠️ VAD 误触发（语音段太短）
        onVADMisfire: () => {
          const durationMs = speechFrameCount.value * 30
          const stats = window._vadStats || { maxProb: 0, aboveThreshold: 0 }
          console.log(`⚠️ [VAD] 误触发回调 (帧数=${speechFrameCount.value}, 时长=${durationMs}ms, maxProb=${stats.maxProb.toFixed(3)}, 需要minSpeechMs=${VAD_CONFIG.minSpeechMs})`)
          
          // 🔧 修复：如果帧数足够多（>30帧=900ms），仍然发送处理信号
          // 这可能是 VAD 库误判，用户确实说了有效内容
          const MIN_VALID_FRAMES = 30 // 约 900ms
          
          if (speechFrameCount.value >= MIN_VALID_FRAMES && isRecordingSessionValid) {
            console.log(`✅ [VAD] 帧数足够 (${speechFrameCount.value} >= ${MIN_VALID_FRAMES})，仍触发处理`)
            if (onSpeechEndCallback) {
              onSpeechEndCallback()
            }
            isRecordingSessionValid = false
          } else {
            // 🆕 修复：帧数不足时也需要通知上层清理空消息
            console.log(`⏭️ [VAD] 帧数不足 (${speechFrameCount.value} < ${MIN_VALID_FRAMES})，触发清理`)
            if (onMisfireCallback) {
              onMisfireCallback(speechFrameCount.value)
            }
            isRecordingSessionValid = false
          }
          
          isSpeaking.value = false
          speechFrameCount.value = 0
        },
      })
      
      isVADReady.value = true
      console.log('✅ [VAD] 初始化成功')
      return true
      
    } catch (e) {
      console.error('❌ [VAD] 初始化失败:', e)
      error.value = e.message
      return false
    }
  }
  
  /**
   * 开始监听
   */
  async function startListening() {
    if (!vad) {
      const success = await initVAD()
      if (!success) return false
    }
    
    try {
      await vad.start()
      isListening.value = true
      setupVisibilityHandler()
      await requestWakeLock()
      console.log('🎧 [VAD] 开始监听')
      return true
    } catch (e) {
      console.error('❌ [VAD] 启动失败:', e)
      error.value = e.message
      return false
    }
  }
  
  /**
   * 停止监听
   */
  function stopListening() {
    if (vad) {
      try {
        vad.pause()
        isListening.value = false
        isSpeaking.value = false
        speechFrameCount.value = 0
        console.log('⏹️ [VAD] 停止监听')
      } catch (e) {
        console.error('❌ [VAD] 停止失败:', e)
      }
    }
  }
  
  /**
   * 暂停 VAD（AI 说话时调用）
   */
  function pauseVAD() {
    isAISpeaking.value = true
    console.log('🔇 [VAD] 暂停 (AI 说话中)')
  }
  
  /**
   * 恢复 VAD（AI 说完后调用）
   * 🆕 增加 1200ms 延迟（原 800ms），更保守地避免回声/尾音
   */
  function resumeVAD() {
    console.log('🔊 [VAD] AI 说完，等待回声消除...')
    // 如果用户已经开始说话（打断 AI），立即恢复，避免丢帧
    if (isSpeaking.value) {
      isAISpeaking.value = false
      console.log(`🔊 [VAD] 立即恢复 (isAISpeaking=${isAISpeaking.value}, isSpeaking=${isSpeaking.value}, vad=${vad ? 'exists' : 'null'}, listening=${isListening.value})`)
      return
    }
    // 🆕 降低延迟：从 1200ms -> 300ms
    // 既然已开启硬件 AEC，且 AI 已停止播放，不需要长时间冷却
    // 解决“AI说完用户立刻说导致开头丢失”的问题
    setTimeout(() => {
      isAISpeaking.value = false
      // 🔧 Fix: 只有在用户没有正在说话时才重置说话状态
      // 避免打断正在进行的录音
      if (!isSpeaking.value) {
        speechFrameCount.value = 0
      }
      console.log(`🔊 [VAD] 恢复监听 (isAISpeaking=${isAISpeaking.value}, isSpeaking=${isSpeaking.value}, vad=${vad ? 'exists' : 'null'}, listening=${isListening.value})`)
    }, 300)
  }
  
  /**
   * 销毁 VAD
   */
  function destroyVAD() {
    if (vad) {
      try {
        vad.destroy()
        vad = null
      } catch (e) {
        console.error('❌ [VAD] 销毁失败:', e)
      }
    }

    if (mediaStream) {
      mediaStream.getTracks().forEach(track => track.stop())
      mediaStream = null
    }

    removeVisibilityHandler()
    releaseWakeLock()

    isVADReady.value = false
    isListening.value = false
    isSpeaking.value = false
    isAISpeaking.value = false
    speechFrameCount.value = 0
    
    console.log('🗑️ [VAD] 已销毁')
  }
  
  // ========== 页面可见性处理（手机切后台/前台）==========
  let visibilityHandler = null
  let wakeLock = null

  function setupVisibilityHandler() {
    if (visibilityHandler) return

    visibilityHandler = async () => {
      if (document.visibilityState === 'visible') {
        console.log('📱 [VAD] 页面恢复前台')
        // 恢复 AudioContext（手机浏览器切后台会暂停）
        if (vad && vad.audioContext && vad.audioContext.state === 'suspended') {
          try {
            await vad.audioContext.resume()
            console.log('✅ [VAD] AudioContext 已恢复')
          } catch (e) {
            console.warn('⚠️ [VAD] AudioContext 恢复失败:', e)
          }
        }
        // 重新获取 Wake Lock
        await requestWakeLock()
      } else {
        console.log('📱 [VAD] 页面切到后台')
      }
    }

    document.addEventListener('visibilitychange', visibilityHandler)
    console.log('✅ [VAD] 页面可见性监听已设置')
  }

  function removeVisibilityHandler() {
    if (visibilityHandler) {
      document.removeEventListener('visibilitychange', visibilityHandler)
      visibilityHandler = null
    }
  }

  async function requestWakeLock() {
    if (!('wakeLock' in navigator)) return
    try {
      wakeLock = await navigator.wakeLock.request('screen')
      wakeLock.addEventListener('release', () => {
        console.log('📱 [VAD] Wake Lock 已释放')
        wakeLock = null
      })
      console.log('✅ [VAD] Wake Lock 已获取')
    } catch (e) {
      console.debug('[VAD] Wake Lock 获取失败（可能在后台）:', e.message)
    }
  }

  function releaseWakeLock() {
    if (wakeLock) {
      wakeLock.release()
      wakeLock = null
    }
  }

  // ========== 学习自 UserGenie: 设备变更监听器 ==========
  let deviceChangeHandler = null
  
  /**
   * 设置设备变更监听（麦克风热插拔）
   * 当用户插拔耳机/麦克风时，重新初始化 VAD
   */
  function setupDeviceChangeListener() {
    if (deviceChangeHandler) {
      console.log('[VAD] 设备变更监听器已存在')
      return
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.addEventListener) {
      console.warn('⚠️ [VAD] navigator.mediaDevices 不可用（需要 HTTPS 或 localhost）')
      return
    }
    
    deviceChangeHandler = async () => {
      console.log('🎤 [VAD] 检测到设备变更，切换音频流...')

      // 🔧 修复：不再销毁重建 VAD，只暂停/恢复来切换底层音频流
      // 这样可以保持录音连续性，避免正在进行的语音识别丢失
      if (!vad) {
        console.warn('⚠️ [VAD] VAD 未初始化，跳过设备变更处理')
        return
      }

      const wasSpeaking = isSpeaking.value
      const wasListening = isListening.value

      if (!wasListening) {
        console.log('[VAD] 未在监听，跳过设备变更处理')
        return
      }

      try {
        // 暂停 VAD（会触发 pauseStream 停止旧音频轨道）
        vad.pause()
        isListening.value = false

        // 等待设备稳定
        await new Promise(resolve => setTimeout(resolve, 500))

        // 恢复 VAD（会触发 resumeStream 获取新设备的音频流）
        await vad.start()
        isListening.value = true

        if (wasSpeaking) {
          console.log('🎤 [VAD] 设备切换完成，之前正在说话，等待 VAD 重新检测')
        }

        console.log('✅ [VAD] 设备变更后音频流已切换（VAD 保持运行）')
      } catch (e) {
        console.error('❌ [VAD] 设备变更处理失败，尝试完整重建:', e)
        // 回退：完整重建
        destroyVAD()
        await new Promise(resolve => setTimeout(resolve, 300))
        const success = await initVAD()
        if (success) {
          await startListening()
          console.log('✅ [VAD] 回退重建成功')
        }
      }
    }
    
    navigator.mediaDevices.addEventListener('devicechange', deviceChangeHandler)
    console.log('✅ [VAD] 设备变更监听器已设置')
  }
  
  /**
   * 移除设备变更监听
   */
  function removeDeviceChangeListener() {
    if (deviceChangeHandler && navigator.mediaDevices && navigator.mediaDevices.removeEventListener) {
      navigator.mediaDevices.removeEventListener('devicechange', deviceChangeHandler)
      deviceChangeHandler = null
      console.log('🗑️ [VAD] 设备变更监听器已移除')
    }
  }
  
  /**
   * 设置回调函数
   * 
   * 🆕 边说边发模式回调说明：
   * - onSpeechStart: 用户开始说话，后端启动流式 ASR
   * - onAudioFrame: 每一帧音频，实时发送到后端
   * - onSpeechEnd: 用户说完（768ms 静默），后端触发 LLM
   * - onInterrupt: 🆕 用户说话达到 0.5秒，触发打断 AI（学习自 UserGenie）
   * - onMisfire: 🆕 VAD 误触发（语音太短），用于清理空消息
   */
  function setCallbacks({ 
    onSpeechStart, 
    onSpeechEnd, 
    onAudioFrame,
    onInterrupt,  // 🆕 打断回调
    onMisfire,    // 🆕 误触发回调
  }) {
    onSpeechStartCallback = onSpeechStart || null
    onSpeechEndCallback = onSpeechEnd || null
    onAudioFrameCallback = onAudioFrame || null
    onInterruptCallback = onInterrupt || null
    onMisfireCallback = onMisfire || null  // 🆕
  }
  
  /**
   * Float32 转 Int16 PCM
   */
  function float32ToInt16(float32Array) {
    const int16Array = new Int16Array(float32Array.length)
    for (let i = 0; i < float32Array.length; i++) {
      const s = Math.max(-1, Math.min(1, float32Array[i]))
      int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
    }
    return int16Array
  }
  
  // 组件卸载时清理
  onUnmounted(() => {
    removeDeviceChangeListener()  // 🆕 移除设备变更监听
    destroyVAD()
  })
  
  /**
   * 🆕 获取 VAD 统计信息（用于调试和阈值调优）
   */
  function getVADStats() {
    const stats = window._vadStats || { 
      frameCount: 0, 
      speechProbs: [], 
      maxProb: 0, 
      minProb: 1,
      aboveThreshold: 0,
      belowThreshold: 0 
    }
    
    const recentProbs = stats.speechProbs.slice(-100)
    const avgProb = recentProbs.length > 0 
      ? recentProbs.reduce((a, b) => a + b, 0) / recentProbs.length 
      : 0
    
    return {
      totalFrames: stats.frameCount,
      maxProb: stats.maxProb,
      minProb: stats.minProb,
      avgProbLast100: avgProb,
      aboveThreshold: stats.aboveThreshold,
      belowThreshold: stats.belowThreshold,
      currentConfig: { ...VAD_CONFIG },
      recommendation: avgProb > 0.4 
        ? `建议 positiveSpeechThreshold: ${(avgProb * 0.8).toFixed(2)}` 
        : '数据不足，请继续录音'
    }
  }
  
  /**
   * 🆕 重置 VAD 统计（开始新一轮测试）
   */
  function resetVADStats() {
    window._vadStats = { 
      frameCount: 0, 
      speechProbs: [], 
      maxProb: 0, 
      minProb: 1,
      aboveThreshold: 0,
      belowThreshold: 0 
    }
    console.log('🔄 [VAD] 统计已重置')
  }
  
  // 🆕 暴露到全局，方便控制台调试
  if (typeof window !== 'undefined') {
    window.getVADStats = getVADStats
    window.resetVADStats = resetVADStats
    window.VAD_CONFIG = VAD_CONFIG
  }
  
  return {
    // 状态
    isVADReady,
    isListening,
    isSpeaking,
    isAISpeaking,
    speechFrameCount,
    error,
    
    // 方法
    initVAD,
    startListening,
    stopListening,
    pauseVAD,
    resumeVAD,
    destroyVAD,
    setCallbacks,
    float32ToInt16,
    setupDeviceChangeListener,     // 🆕 设备变更监听
    removeDeviceChangeListener,    // 🆕 移除设备变更监听
    setupVisibilityHandler,        // 📱 页面可见性处理
    requestWakeLock,               // 📱 防止设备休眠
    releaseWakeLock,               // 📱 释放 Wake Lock
    getVADStats,                   // 🆕 获取统计
    resetVADStats,                 // 🆕 重置统计
    
    // 配置（供外部读取）
    VAD_CONFIG,
  }
}
