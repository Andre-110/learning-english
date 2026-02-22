import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// 获取 API 基础路径（处理子路径部署）
const API_BASE = import.meta.env.PROD ? '/english' : ''

export const useAuthStore = defineStore('auth', () => {
  // 状态
  const token = ref(localStorage.getItem('token') || null)
  const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))
  const loading = ref(false)
  const error = ref(null)
  
  // 🆕 Token 验证状态：防止页面闪烁
  const isVerifying = ref(true)  // 初始为 true，验证完成后设为 false
  const isVerified = ref(false)  // 验证是否已完成

  // 计算属性
  // 🔧 修复：只有验证完成后才返回登录状态
  const isLoggedIn = computed(() => {
    if (!isVerified.value) return false  // 验证未完成，视为未登录
    return !!token.value && !!user.value
  })
  const username = computed(() => user.value?.username || '')
  const userId = computed(() => user.value?.user_id || '')

  // 方法
  async function login(usernameOrEmail, password) {
    loading.value = true
    error.value = null
    
    try {
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: usernameOrEmail, password })
      })
      
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || '登录失败')
      }
      
      const data = await response.json()
      setAuth(data.access_token, {
        user_id: data.user_id,
        username: data.username
      })
      
      return true
    } catch (e) {
      error.value = e.message
      return false
    } finally {
      loading.value = false
    }
  }

  async function register(username, email, password) {
    loading.value = true
    error.value = null
    
    try {
      const response = await fetch(`${API_BASE}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email: email || null, password })
      })
      
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || '注册失败')
      }
      
      const data = await response.json()
      setAuth(data.access_token, {
        user_id: data.user_id,
        username: data.username
      })
      
      return true
    } catch (e) {
      error.value = e.message
      return false
    } finally {
      loading.value = false
    }
  }

  async function verifyToken() {
    isVerifying.value = true
    
    try {
      if (!token.value) {
        isVerified.value = true
        isVerifying.value = false
        return false
      }
      
      const response = await fetch(`${API_BASE}/auth/me`, {
        headers: { 'Authorization': `Bearer ${token.value}` }
      })
      
      if (!response.ok) {
        logout()
        isVerified.value = true
        isVerifying.value = false
        return false
      }
      
      const data = await response.json()
      user.value = {
        user_id: data.user_id,
        username: data.username,
        email: data.email
      }
      localStorage.setItem('user', JSON.stringify(user.value))
      
      isVerified.value = true
      isVerifying.value = false
      return true
    } catch (e) {
      logout()
      isVerified.value = true
      isVerifying.value = false
      return false
    }
  }

  function setAuth(newToken, newUser) {
    token.value = newToken
    user.value = newUser
    localStorage.setItem('token', newToken)
    localStorage.setItem('user', JSON.stringify(newUser))
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    // 注意：不重置 isVerified，保持登出后可以正常判断
  }

  function getAuthHeaders() {
    return token.value ? { 'Authorization': `Bearer ${token.value}` } : {}
  }

  return {
    // 状态
    token,
    user,
    loading,
    error,
    isVerifying,  // 🆕 验证中状态（用于显示加载）
    // 计算属性
    isLoggedIn,
    username,
    userId,
    // 方法
    login,
    register,
    verifyToken,
    logout,
    getAuthHeaders
  }
})

