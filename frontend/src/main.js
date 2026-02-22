import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import './assets/main.css'

// ==================== 前端日志上报 ====================
const API_BASE = import.meta.env.PROD ? '/english' : ''

// 日志上报函数
async function reportLog(level, type, message, data = null) {
  try {
    await fetch(`${API_BASE}/api/frontend-log`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        level,
        type,
        message,
        data,
        timestamp: Date.now(),
        url: window.location.href,
        userAgent: navigator.userAgent
      })
    })
  } catch (e) {
    // 静默失败，避免死循环
    console.warn('[LogReport] 上报失败:', e)
  }
}

// 全局错误捕获
window.onerror = function(message, source, lineno, colno, error) {
  reportLog('error', 'js_error', message, {
    source,
    lineno,
    colno,
    stack: error?.stack
  })
  return false // 不阻止默认处理
}

// Promise 未捕获异常
window.onunhandledrejection = function(event) {
  reportLog('error', 'promise_rejection', event.reason?.message || String(event.reason), {
    stack: event.reason?.stack
  })
}

// 性能指标上报（页面加载完成后）
window.addEventListener('load', () => {
  // 延迟上报，等待性能数据稳定
  setTimeout(() => {
    try {
      const perf = performance.getEntriesByType('navigation')[0]
      const paint = performance.getEntriesByType('paint')
      
      const metrics = {
        // 页面加载时间
        dns: Math.round(perf?.domainLookupEnd - perf?.domainLookupStart || 0),
        tcp: Math.round(perf?.connectEnd - perf?.connectStart || 0),
        ttfb: Math.round(perf?.responseStart - perf?.requestStart || 0),
        domReady: Math.round(perf?.domContentLoadedEventEnd - perf?.startTime || 0),
        load: Math.round(perf?.loadEventEnd - perf?.startTime || 0),
        
        // 渲染指标
        fcp: Math.round(paint.find(p => p.name === 'first-contentful-paint')?.startTime || 0),
        fp: Math.round(paint.find(p => p.name === 'first-paint')?.startTime || 0),
      }
      
      reportLog('info', 'performance', '页面性能指标', metrics)
      console.log('📊 [Performance]', metrics)
    } catch (e) {
      console.warn('[Performance] 获取性能指标失败:', e)
    }
  }, 2000)
})

// 资源加载错误捕获
window.addEventListener('error', (event) => {
  if (event.target && (event.target.tagName === 'IMG' || event.target.tagName === 'SCRIPT' || event.target.tagName === 'LINK')) {
    reportLog('warning', 'resource_error', `资源加载失败: ${event.target.src || event.target.href}`, {
      tagName: event.target.tagName,
      src: event.target.src || event.target.href
    })
  }
}, true)

// ==================== Vue 应用 ====================
const app = createApp(App)

// Vue 错误处理
app.config.errorHandler = (err, instance, info) => {
  reportLog('error', 'vue_error', err.message, {
    stack: err.stack,
    info,
    component: instance?.$options?.name
  })
  console.error('[Vue Error]', err)
}

app.use(createPinia())
app.mount('#app')

