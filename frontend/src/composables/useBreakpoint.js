/**
 * 响应式断点，用于 Web / 手机两套 UI 切换。
 * 与 CSS 保持一致：<= 768px 视为手机端；<= 992px 评估侧栏为浮层模式（需按钮打开）。
 */
import { ref, onMounted, onUnmounted } from 'vue'

const MOBILE_MAX = 768
const EVAL_OVERLAY_MAX = 992

function getIsMobile() {
  if (typeof window === 'undefined') return false
  return window.innerWidth <= MOBILE_MAX
}

function getIsEvalOverlay() {
  if (typeof window === 'undefined') return false
  return window.innerWidth <= EVAL_OVERLAY_MAX
}

export function useBreakpoint() {
  const isMobile = ref(getIsMobile())
  const isEvalOverlay = ref(getIsEvalOverlay())

  function update() {
    isMobile.value = getIsMobile()
    isEvalOverlay.value = getIsEvalOverlay()
  }

  onMounted(() => {
    window.addEventListener('resize', update)
    update()
  })

  onUnmounted(() => {
    window.removeEventListener('resize', update)
  })

  return { isMobile, isEvalOverlay }
}
