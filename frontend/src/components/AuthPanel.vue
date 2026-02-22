<template>
  <div class="auth-container">
    <div class="auth-card card animate-slideUp">
      <div class="auth-header">
        <h2>{{ isLogin ? '欢迎回来' : '创建账户' }}</h2>
        <p>{{ isLogin ? '登录以继续练习英语' : '开始你的英语学习之旅' }}</p>
      </div>
      
      <!-- 标签切换 -->
      <div class="auth-tabs">
        <button 
          class="tab" 
          :class="{ active: isLogin }"
          @click="isLogin = true"
        >
          登录
        </button>
        <button 
          class="tab" 
          :class="{ active: !isLogin }"
          @click="isLogin = false"
        >
          注册
        </button>
      </div>
      
      <!-- 登录表单 -->
      <form v-if="isLogin" @submit.prevent="handleLogin" class="auth-form">
        <div class="form-group">
          <label for="login-username">用户名或邮箱</label>
          <input 
            id="login-username"
            v-model="loginForm.username"
            type="text" 
            class="input"
            placeholder="输入用户名或邮箱"
            required
          >
        </div>
        
        <div class="form-group">
          <label for="login-password">密码</label>
          <input 
            id="login-password"
            v-model="loginForm.password"
            type="password" 
            class="input"
            placeholder="输入密码"
            required
          >
        </div>
        
        <button type="submit" class="btn btn-primary submit-btn" :disabled="auth.loading">
          <span v-if="auth.loading" class="loading-spinner"></span>
          {{ auth.loading ? '登录中...' : '登录' }}
        </button>
      </form>
      
      <!-- 注册表单 -->
      <form v-else @submit.prevent="handleRegister" class="auth-form">
        <div class="form-group">
          <label for="register-username">用户名</label>
          <input 
            id="register-username"
            v-model="registerForm.username"
            type="text" 
            class="input"
            placeholder="至少3个字符"
            minlength="3"
            required
          >
        </div>
        
        <div class="form-group">
          <label for="register-email">邮箱 <span class="optional">(可选)</span></label>
          <input 
            id="register-email"
            v-model="registerForm.email"
            type="email" 
            class="input"
            placeholder="example@email.com"
          >
        </div>
        
        <div class="form-group">
          <label for="register-password">密码</label>
          <input 
            id="register-password"
            v-model="registerForm.password"
            type="password" 
            class="input"
            placeholder="至少6个字符"
            minlength="6"
            required
          >
        </div>
        
        <div class="form-group">
          <label for="register-confirm">确认密码</label>
          <input 
            id="register-confirm"
            v-model="registerForm.confirmPassword"
            type="password" 
            class="input"
            placeholder="再次输入密码"
            required
          >
        </div>
        
        <p v-if="registerError" class="error-text">{{ registerError }}</p>
        
        <button type="submit" class="btn btn-primary submit-btn" :disabled="auth.loading">
          <span v-if="auth.loading" class="loading-spinner"></span>
          {{ auth.loading ? '注册中...' : '注册' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()

const isLogin = ref(true)
const registerError = ref('')

const loginForm = reactive({
  username: '',
  password: ''
})

const registerForm = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

async function handleLogin() {
  const success = await auth.login(loginForm.username, loginForm.password)
  if (success) {
    loginForm.username = ''
    loginForm.password = ''
  }
}

async function handleRegister() {
  registerError.value = ''
  
  if (registerForm.username.length < 3) {
    registerError.value = '用户名至少需要3个字符'
    return
  }
  
  if (registerForm.password.length < 6) {
    registerError.value = '密码至少需要6个字符'
    return
  }
  
  if (registerForm.password !== registerForm.confirmPassword) {
    registerError.value = '两次输入的密码不一致'
    return
  }
  
  const success = await auth.register(
    registerForm.username,
    registerForm.email,
    registerForm.password
  )
  
  if (success) {
    registerForm.username = ''
    registerForm.email = ''
    registerForm.password = ''
    registerForm.confirmPassword = ''
  }
}
</script>

<style scoped>
.auth-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: calc(100vh - 200px);
}

.auth-card {
  width: 100%;
  max-width: 420px;
  padding: 40px;
}

.auth-header {
  text-align: center;
  margin-bottom: 32px;
}

.auth-header h2 {
  font-size: 1.75rem;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.auth-header p {
  color: var(--text-secondary);
}

.auth-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  padding: 4px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
}

.tab {
  flex: 1;
  padding: 10px;
  font-family: inherit;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-secondary);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.tab.active {
  background: var(--bg-secondary);
  color: var(--primary);
  box-shadow: var(--shadow-sm);
}

.tab:hover:not(.active) {
  color: var(--text-primary);
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
}

.optional {
  font-weight: 400;
  color: var(--text-muted);
}

.submit-btn {
  margin-top: 8px;
  padding: 14px;
}

.error-text {
  color: var(--error);
  font-size: 0.85rem;
  margin: 0;
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>

