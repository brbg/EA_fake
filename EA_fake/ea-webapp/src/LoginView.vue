<script setup lang="ts">
// 登录 / 注册页。作为主界面（App.vue）的登录门使用：
// 未登录时全屏展示，登录或注册成功后把 session 存入 sessionStorage 并通知父组件进入主界面。
import { ref, computed } from 'vue'

const emit = defineEmits<{
  (e: 'authenticated', user: { username: string; email: string }): void
}>()

type AuthMode = 'login' | 'register'
const mode = ref<AuthMode>('login')

const form = ref({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

const errorMsg = ref('')
const successMsg = ref('')
const loading = ref(false)
const showPassword = ref(false)
const showConfirmPassword = ref(false)

const title = computed(() => (mode.value === 'login' ? '登录到工作台' : '创建新账号'))
const submitText = computed(() => {
  if (loading.value) return mode.value === 'login' ? '登录中...' : '注册中...'
  return mode.value === 'login' ? '登 录' : '注 册'
})

const switchMode = (m: AuthMode) => {
  mode.value = m
  errorMsg.value = ''
  successMsg.value = ''
}

// 本地校验
const validate = (): string => {
  const { username, email, password, confirmPassword } = form.value
  if (!username.trim()) return '请输入用户名'
  if (mode.value === 'register') {
    if (username.trim().length < 2) return '用户名至少 2 个字符'
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) return '请输入有效的邮箱地址'
    if (password.length < 6) return '密码至少 6 位'
    if (password !== confirmPassword) return '两次输入的密码不一致'
  } else {
    if (!password) return '请输入密码'
  }
  return ''
}

const doAuth = async () => {
  errorMsg.value = ''
  successMsg.value = ''
  const err = validate()
  if (err) {
    errorMsg.value = err
    return
  }

  loading.value = true
  try {
    const isLogin = mode.value === 'login'
    const body = isLogin
      ? { username: form.value.username.trim(), password: form.value.password }
      : {
          username: form.value.username.trim(),
          email: form.value.email.trim(),
          password: form.value.password
        }

    const res = await fetch(isLogin ? '/api/auth/login' : '/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })

    const data = await res.json()
    if (!res.ok) {
      errorMsg.value = data.error || '请求失败，请稍后重试'
      return
    }

    // 登录成功：保存会话（register 不返回 session_id，注册后自动切到登录态，提示用户直接登录）
    if (data.session_id) {
      sessionStorage.setItem('sessionId', data.session_id)
      sessionStorage.setItem('ea_user', JSON.stringify(data.user || {}))
      emit('authenticated', {
        username: data.user?.username || form.value.username.trim(),
        email: data.user?.email || ''
      })
    } else {
      // 注册成功 → 自动切换到登录页，填好用户名，方便直接登录
      mode.value = 'login'
      form.value.confirmPassword = ''
      form.value.password = ''
      successMsg.value = (data.message || '注册成功') + '，请登录'
    }
  } catch (e) {
    errorMsg.value = '无法连接服务器，请确认后端已启动'
  } finally {
    loading.value = false
  }
}

const submit = () => {
  if (loading.value) return
  doAuth()
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-glow auth-glow-1"></div>
    <div class="auth-glow auth-glow-2"></div>
    <div class="auth-grid"></div>

    <div class="auth-card">
      <div class="auth-brand">
        <div class="brand-mark">
          <i class="fas fa-project-diagram"></i>
        </div>
        <h1 class="brand-title">AI 原生 Enterprise Architect</h1>
        <p class="brand-sub">智能企业架构建模平台</p>
      </div>

      <div class="mode-tabs">
        <button
          :class="['mode-tab', { active: mode === 'login' }]"
          @click="switchMode('login')"
        >
          登录
        </button>
        <button
          :class="['mode-tab', { active: mode === 'register' }]"
          @click="switchMode('register')"
        >
          注册
        </button>
      </div>

      <h2 class="auth-title">{{ title }}</h2>

      <form class="auth-form" @submit.prevent="submit">
        <div class="form-field">
          <label for="auth-username">用户名</label>
          <div class="input-wrap">
            <i class="fas fa-user input-icon"></i>
            <input
              id="auth-username"
              v-model="form.username"
              type="text"
              placeholder="请输入用户名"
              autocomplete="username"
            />
          </div>
        </div>

        <div v-if="mode === 'register'" class="form-field">
          <label for="auth-email">邮箱</label>
          <div class="input-wrap">
            <i class="fas fa-envelope input-icon"></i>
            <input
              id="auth-email"
              v-model="form.email"
              type="email"
              placeholder="name@example.com"
              autocomplete="email"
            />
          </div>
        </div>

        <div class="form-field">
          <label for="auth-password">密码</label>
          <div class="input-wrap">
            <i class="fas fa-lock input-icon"></i>
            <input
              id="auth-password"
              v-model="form.password"
              :type="showPassword ? 'text' : 'password'"
              placeholder="请输入密码"
              :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
            />
            <button
              type="button"
              class="eye-toggle"
              @click="showPassword = !showPassword"
              :title="showPassword ? '隐藏密码' : '显示密码'"
            >
              <i :class="showPassword ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
            </button>
          </div>
        </div>

        <div v-if="mode === 'register'" class="form-field">
          <label for="auth-confirm">确认密码</label>
          <div class="input-wrap">
            <i class="fas fa-lock input-icon"></i>
            <input
              id="auth-confirm"
              v-model="form.confirmPassword"
              :type="showConfirmPassword ? 'text' : 'password'"
              placeholder="再次输入密码"
              autocomplete="new-password"
            />
            <button
              type="button"
              class="eye-toggle"
              @click="showConfirmPassword = !showConfirmPassword"
              :title="showConfirmPassword ? '隐藏密码' : '显示密码'"
            >
              <i :class="showConfirmPassword ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
            </button>
          </div>
        </div>

        <div v-if="successMsg" class="auth-success">
          <i class="fas fa-check-circle"></i> {{ successMsg }}
        </div>

        <div v-if="errorMsg" class="auth-error">
          <i class="fas fa-exclamation-circle"></i> {{ errorMsg }}
        </div>

        <button class="auth-submit" type="submit" :disabled="loading">
          <i v-if="loading" class="fas fa-spinner fa-spin"></i>
          <i v-else :class="mode === 'login' ? 'fas fa-sign-in-alt' : 'fas fa-user-plus'"></i>
          {{ submitText }}
        </button>
      </form>

      <p class="auth-switch">
        <template v-if="mode === 'login'">
          还没有账号？
          <button type="button" class="link-btn" @click="switchMode('register')">去注册</button>
        </template>
        <template v-else>
          已有账号？
          <button type="button" class="link-btn" @click="switchMode('login')">去登录</button>
        </template>
      </p>

      <p class="auth-foot">本地演示版 · 数据存储于本机 SQLite</p>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  overflow: hidden;
  background: linear-gradient(135deg, #312e81 0%, #4c1d95 50%, #6d28d9 100%);
}

/* 背景光晕 + 网格纹理，让纯渐变更高级 */
.auth-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
  opacity: 0.5;
  pointer-events: none;
}
.auth-glow-1 {
  width: 480px;
  height: 480px;
  top: -120px;
  left: -100px;
  background: #6366f1;
}
.auth-glow-2 {
  width: 520px;
  height: 520px;
  bottom: -160px;
  right: -120px;
  background: #ec4899;
  opacity: 0.35;
}
.auth-grid {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.05) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(ellipse at center, black 20%, transparent 75%);
  -webkit-mask-image: radial-gradient(ellipse at center, black 20%, transparent 75%);
}

.auth-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 420px;
  background: #fff;
  border-radius: 20px;
  box-shadow: 0 25px 60px rgba(0, 0, 0, 0.35);
  padding: 36px 36px 28px;
}

.auth-brand {
  text-align: center;
  margin-bottom: 24px;
}
.brand-mark {
  width: 56px;
  height: 56px;
  margin: 0 auto 12px;
  border-radius: 16px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 26px;
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.4);
}
.brand-title {
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
}
.brand-sub {
  margin-top: 6px;
  font-size: 13px;
  color: #64748b;
}

.mode-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  background: #f1f5f9;
  border-radius: 10px;
  padding: 5px;
  margin-bottom: 22px;
}
.mode-tab {
  border: none;
  background: transparent;
  padding: 9px 0;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s;
}
.mode-tab.active {
  background: #fff;
  color: #6366f1;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.1);
}

.auth-title {
  font-size: 16px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 18px;
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-field label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: #475569;
  margin-bottom: 6px;
}

.input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}
.input-icon {
  position: absolute;
  left: 12px;
  color: #94a3b8;
  font-size: 14px;
  pointer-events: none;
}
.input-wrap input {
  width: 100%;
  padding: 11px 12px 11px 38px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  font-size: 14px;
  color: #1e293b;
  background: #f8fafc;
  outline: none;
  transition: all 0.2s;
}
.input-wrap input:focus {
  border-color: #6366f1;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}
.eye-toggle {
  position: absolute;
  right: 8px;
  border: none;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  padding: 6px 8px;
  font-size: 14px;
}
.eye-toggle:hover {
  color: #6366f1;
}

.auth-success {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  color: #059669;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 13px;
}

.auth-error {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #dc2626;
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 13px;
}

.auth-submit {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 6px 18px rgba(99, 102, 241, 0.35);
}
.auth-submit:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.45);
}
.auth-submit:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.auth-switch {
  text-align: center;
  margin-top: 18px;
  font-size: 13px;
  color: #64748b;
}
.link-btn {
  border: none;
  background: transparent;
  color: #6366f1;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  padding: 0 2px;
}
.link-btn:hover {
  text-decoration: underline;
}

.auth-foot {
  text-align: center;
  margin-top: 14px;
  font-size: 12px;
  color: #94a3b8;
}
</style>
