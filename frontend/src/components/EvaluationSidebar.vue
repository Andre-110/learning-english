<template>
  <!-- 手机端浮层：点击遮罩关闭 -->
  <div v-if="mobileOpen" class="eval-mobile-backdrop" @click="emit('close')" aria-hidden="true"></div>
  <div 
    class="evaluation-sidebar" 
    :class="{ collapsed: isCollapsed, 'mobile-open': mobileOpen }"
    :style="mobileOpen ? {} : { width: isCollapsed ? '40px' : sidebarWidth + 'px', minWidth: isCollapsed ? '40px' : sidebarWidth + 'px' }"
  >
    <!-- 拖动调整宽度的把手 -->
    <div 
      class="resize-handle"
      v-show="!isCollapsed"
      @mousedown="startResize"
    ></div>
    
    <!-- 折叠按钮 -->
    <button class="collapse-btn" @click="toggleCollapse">
      {{ isCollapsed ? '◀' : '▶' }}
    </button>
    
    <!-- 侧边栏内容 -->
    <div class="sidebar-content" v-show="!isCollapsed || mobileOpen">
      <div class="sidebar-header">
        <h3>📊 评估反馈</h3>
        <button v-if="mobileOpen" class="mobile-close-btn" @click="emit('close')" aria-label="关闭">✕</button>
        <span v-else class="eval-count">{{ evaluations.length }} 条</span>
      </div>
      
      <!-- 评估列表 -->
      <div class="evaluations-list" ref="evaluationsContainer">
        <TransitionGroup name="eval">
          <div 
            v-for="(evaluation, index) in evaluations" 
            :key="evaluation.messageRoundId"
            class="evaluation-card"
            :class="{ highlighted: highlightedId === evaluation.messageRoundId }"
            :data-round-id="evaluation.messageRoundId"
            @mouseenter="highlightMessage(evaluation.messageRoundId)"
            @mouseleave="unhighlightMessage"
          >
            <!-- 牵引线指示器 -->
            <div class="connection-indicator">
              <span class="round-number">#{{ index + 1 }}</span>
            </div>
            
            <!-- 评估内容 -->
            <div class="eval-content">
              <!-- 🔴 已隐藏分数和等级显示 -->
              <!-- 只保留延迟信息（调试用，可选显示） -->
              <div v-if="evaluation.latency" class="latency-info">
                <span class="latency">{{ evaluation.latency }}s</span>
              </div>
              
              <!-- 转录文本 -->
              <div v-if="evaluation.transcription" class="transcription-preview">
                "{{ truncateText(evaluation.transcription, 50) }}"
              </div>
              
              <!-- 韵律/发音反馈 -->
              <div v-if="evaluation.prosody_feedback" class="prosody-feedback">
                🎤 {{ evaluation.prosody_feedback }}
              </div>
              
              <!-- 鼓励语 -->
              <div v-if="evaluation.encouragement" class="encouragement">
                🌟 {{ evaluation.encouragement }}
              </div>
              
              <!-- 纠错建议 -->
              <div v-if="getValidCorrections(evaluation.corrections).length" class="corrections">
                <div v-for="(c, idx) in getValidCorrections(evaluation.corrections)" :key="idx" class="correction-item" :class="'type-' + (c.type || 'grammar')">
                  <span class="correction-type">{{ getCorrectionTypeIcon(c.type) }}</span>
                  <span class="original">{{ c.original }}</span>
                  <span class="arrow">→</span>
                  <span class="corrected">{{ c.corrected }}</span>
                  <div v-if="c.explanation" class="explanation">💡 {{ c.explanation }}</div>
                </div>
              </div>
              
              <!-- 好的表达 -->
              <div v-if="evaluation.good_expressions?.length" class="good-expressions">
                <span class="label">✨ 亮点:</span>
                <span v-for="(expr, idx) in evaluation.good_expressions" :key="idx" class="expr-tag">
                  {{ formatGoodExpression(expr) }}
                </span>
              </div>
            </div>
          </div>
        </TransitionGroup>
        
        <!-- 等待评估中的提示 -->
        <div v-if="pendingCount > 0" class="pending-indicator">
          <div class="spinner"></div>
          <span>{{ pendingCount }} 条评估处理中...</span>
        </div>
        
        <!-- 空状态 -->
        <div v-if="evaluations.length === 0 && pendingCount === 0" class="empty-state">
          <div class="empty-icon">📝</div>
          <p>开始对话后，评估反馈将显示在这里</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  evaluations: {
    type: Array,
    default: () => []
  },
  pendingCount: {
    type: Number,
    default: 0
  },
  /** 手机端由外部控制浮层显示 */
  mobileOpen: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['highlight-message', 'unhighlight-message', 'close'])

const isCollapsed = ref(false)
const highlightedId = ref(null)
const evaluationsContainer = ref(null)

// 侧边栏宽度（可拖动调整）
const sidebarWidth = ref(320)
const minWidth = 240
const maxWidth = 600
const isResizing = ref(false)

// 切换折叠状态
function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
}

// 开始拖动调整宽度
function startResize(e) {
  isResizing.value = true
  const startX = e.clientX
  const startWidth = sidebarWidth.value
  
  const onMouseMove = (moveEvent) => {
    // 向左拖动增加宽度（因为侧边栏在右边）
    const delta = startX - moveEvent.clientX
    const newWidth = Math.min(maxWidth, Math.max(minWidth, startWidth + delta))
    sidebarWidth.value = newWidth
  }
  
  const onMouseUp = () => {
    isResizing.value = false
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    
    // 保存宽度到 localStorage
    localStorage.setItem('evalSidebarWidth', sidebarWidth.value.toString())
  }
  
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
  document.body.style.cursor = 'ew-resize'
  document.body.style.userSelect = 'none'
}

// 从 localStorage 恢复宽度
const savedWidth = localStorage.getItem('evalSidebarWidth')
if (savedWidth) {
  const parsed = parseInt(savedWidth, 10)
  if (!isNaN(parsed) && parsed >= minWidth && parsed <= maxWidth) {
    sidebarWidth.value = parsed
  }
}

// 高亮对应的用户消息
function highlightMessage(messageRoundId) {
  highlightedId.value = messageRoundId
  emit('highlight-message', messageRoundId)
}

// 取消高亮
function unhighlightMessage() {
  highlightedId.value = null
  emit('unhighlight-message')
}

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

// 截断文本
function truncateText(text, maxLength) {
  if (!text) return ''
  return text.length > maxLength ? text.substring(0, maxLength) + '...' : text
}

// 过滤无效的修改建议
function getValidCorrections(corrections) {
  if (!corrections || !Array.isArray(corrections)) return []
  return corrections.filter(c => {
    if (!c.original || !c.corrected) return false
    const orig = c.original.trim().toLowerCase()
    const corr = c.corrected.trim().toLowerCase()
    return orig !== corr
  }).slice(0, 3) // 最多显示3条
}

// 格式化好的表达
function formatGoodExpression(expr) {
  if (typeof expr === 'string') return expr
  if (typeof expr === 'object' && expr !== null) {
    return expr.expression || JSON.stringify(expr)
  }
  return String(expr)
}

// 获取纠错类型图标
function getCorrectionTypeIcon(type) {
  switch (type) {
    case 'pronunciation':
      return '🗣️'  // 发音
    case 'grammar':
      return '📝'  // 语法
    case 'vocabulary':
      return '📚'  // 词汇
    default:
      return '✏️'
  }
}

// 新评估到达时滚动到底部
watch(() => props.evaluations.length, async () => {
  await nextTick()
  if (evaluationsContainer.value) {
    evaluationsContainer.value.scrollTo({
      top: evaluationsContainer.value.scrollHeight,
      behavior: 'smooth'
    })
  }
})
</script>

<style scoped>
.evaluation-sidebar {
  height: 100%;
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-light);
  display: flex;
  flex-direction: column;
  position: relative;
  transition: width 0.15s ease, min-width 0.15s ease;
  flex-shrink: 0;
}

.evaluation-sidebar.collapsed {
  width: 40px !important;
  min-width: 40px !important;
}

/* 拖动调整宽度的把手 */
.resize-handle {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: ew-resize;
  background: transparent;
  z-index: 20;
  transition: background 0.2s;
}

.resize-handle:hover,
.resize-handle:active {
  background: var(--primary);
  opacity: 0.5;
}

.collapse-btn {
  position: absolute;
  left: -12px;
  top: 50%;
  transform: translateY(-50%);
  width: 24px;
  height: 48px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 4px 0 0 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--text-muted);
  z-index: 10;
  transition: all 0.2s;
}

.collapse-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.sidebar-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sidebar-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.eval-count {
  font-size: 0.8rem;
  color: var(--text-muted);
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.evaluations-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.evaluation-card {
  background: var(--bg-primary);
  border-radius: var(--radius-md);
  padding: 12px;
  margin-bottom: 12px;
  border: 1px solid var(--border-light);
  transition: all 0.2s;
  position: relative;
}

.evaluation-card:hover {
  border-color: var(--primary);
  box-shadow: 0 2px 8px rgba(78, 205, 196, 0.15);
}

.evaluation-card.highlighted {
  border-color: var(--primary);
  background: rgba(78, 205, 196, 0.05);
  box-shadow: 0 0 0 2px rgba(78, 205, 196, 0.2);
}

/* 牵引线指示器 */
.connection-indicator {
  position: absolute;
  left: -20px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
}

.round-number {
  width: 24px;
  height: 24px;
  background: var(--primary);
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.7rem;
  font-weight: 600;
}

.eval-content {
  margin-left: 8px;
}

.score-section {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.score {
  font-size: 1.1rem;
  font-weight: 700;
}

/* CEFR 等级对应的分数颜色 */
.score-c2 { color: #FFD700; }  /* C2: 金色 */
.score-c1 { color: #9B59B6; }  /* C1: 紫色 */
.score-b2 { color: #27AE60; }  /* B2: 深绿 */
.score-b1 { color: #3498DB; }  /* B1: 蓝色 */
.score-a2 { color: #F39C12; }  /* A2: 橙色 */
.score-a1 { color: #E74C3C; }  /* A1: 红色 */

.level {
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  font-weight: 600;
}

/* 6种 CEFR 等级颜色 */
.level.level-a1 { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
.level.level-a2 { background: rgba(246, 173, 85, 0.2); color: #f6ad55; }
.level.level-b1 { background: rgba(99, 179, 237, 0.2); color: #63b3ed; }
.level.level-b2 { background: rgba(56, 189, 248, 0.2); color: #38bdf8; }
.level.level-c1 { background: rgba(72, 187, 120, 0.2); color: #48bb78; }
.level.level-c2 { background: rgba(168, 85, 247, 0.2); color: #a855f7; }

.latency {
  font-size: 0.7rem;
  color: var(--text-muted);
  margin-left: auto;
}

.transcription-preview {
  font-size: 0.85rem;
  color: var(--text-secondary);
  font-style: italic;
  margin-bottom: 8px;
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
}

.prosody-feedback {
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-bottom: 8px;
  padding: 6px 10px;
  background: rgba(147, 112, 219, 0.1);
  border-left: 2px solid #9370DB;
  border-radius: var(--radius-sm);
}

.encouragement {
  font-size: 0.85rem;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.corrections {
  margin-bottom: 8px;
}

.correction-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
  padding: 6px 8px;
  font-size: 0.8rem;
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  border-left: 2px solid var(--text-muted);
}

/* 发音类型纠错 - 紫色 */
.correction-item.type-pronunciation {
  background: rgba(147, 112, 219, 0.08);
  border-left-color: #9370DB;
}

/* 语法类型纠错 - 蓝色 */
.correction-item.type-grammar {
  background: rgba(66, 153, 225, 0.08);
  border-left-color: #4299E1;
}

/* 词汇类型纠错 - 橙色 */
.correction-item.type-vocabulary {
  background: rgba(237, 137, 54, 0.08);
  border-left-color: #ED8936;
}

.correction-type {
  flex-shrink: 0;
  margin-right: 4px;
}

.correction-item .original {
  text-decoration: line-through;
  color: var(--text-muted);
}

.correction-item .arrow {
  color: var(--text-muted);
}

.correction-item .corrected {
  color: var(--success);
  font-weight: 500;
}

.correction-item .explanation {
  flex-basis: 100%;
  color: var(--text-secondary);
  font-size: 0.75rem;
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px dashed var(--border-light);
}

.good-expressions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  font-size: 0.8rem;
}

.good-expressions .label {
  color: var(--text-secondary);
}

.good-expressions .expr-tag {
  padding: 2px 6px;
  background: rgba(72, 187, 120, 0.15);
  color: var(--success);
  border-radius: var(--radius-full);
  font-size: 0.75rem;
}

/* 等待指示器 */
.pending-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: var(--text-muted);
  text-align: center;
}

.empty-icon {
  font-size: 2rem;
  margin-bottom: 12px;
  opacity: 0.5;
}

/* 过渡动画 - 进入、离开、移动 */
.eval-enter-active,
.eval-leave-active {
  transition: all 0.4s ease;
}

.eval-enter-from {
  opacity: 0;
  transform: translateX(30px);
}

.eval-leave-to {
  opacity: 0;
  transform: translateX(-30px);
  height: 0;
  margin: 0;
  padding: 0;
  overflow: hidden;
}

/* 列表项移动时的平滑过渡 */
.eval-move {
  transition: transform 0.4s ease;
}

/* 手机端：改为右侧滑出浮层，由工具栏按钮打开 */
@media (max-width: 992px) {
  .evaluation-sidebar {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(90vw, 360px);
    max-width: 360px;
    height: 100vh;
    height: 100dvh;
    z-index: 1001;
    transform: translateX(100%);
    transition: transform 0.25s ease;
    box-shadow: -4px 0 20px rgba(0, 0, 0, 0.15);
    border-left: 1px solid var(--border-light);
  }

  .evaluation-sidebar.mobile-open {
    transform: translateX(0);
  }

  .eval-mobile-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 1000;
  }

  .evaluation-sidebar .resize-handle,
  .evaluation-sidebar .collapse-btn {
    display: none;
  }

  .evaluation-sidebar .sidebar-content {
    padding-top: env(safe-area-inset-top, 0);
  }

  .mobile-close-btn {
    width: 36px;
    height: 36px;
    padding: 0;
    border: none;
    border-radius: var(--radius-md);
    background: var(--bg-tertiary);
    color: var(--text-primary);
    font-size: 1.2rem;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }

  .mobile-close-btn:hover {
    background: var(--border-light);
  }

  .evaluation-sidebar.collapsed {
    width: min(90vw, 360px) !important;
    min-width: auto !important;
  }
}
</style>

