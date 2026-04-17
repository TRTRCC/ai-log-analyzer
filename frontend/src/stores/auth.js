import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from '@/utils/axios'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const refreshToken = ref(localStorage.getItem('refreshToken') || '')
  const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))

  const isLoggedIn = computed(() => !!token.value)
  const userRole = computed(() => user.value?.role || '')
  const userName = computed(() => user.value?.username || '')
  const userEmail = computed(() => user.value?.email || '')

  async function login(credentials) {
    try {
      const response = await axios.post('/api/v1/auth/login', credentials)
      const { access_token, refresh_token, user: userData } = response.data

      token.value = access_token
      refreshToken.value = refresh_token
      user.value = userData

      localStorage.setItem('token', access_token)
      localStorage.setItem('refreshToken', refresh_token)
      localStorage.setItem('user', JSON.stringify(userData))

      return { success: true }
    } catch (error) {
      return { success: false, error: error.response?.data?.detail || 'Login failed' }
    }
  }

  async function logout() {
    try {
      await axios.post('/api/v1/auth/logout')
    } catch (error) {
      console.error('Logout error:', error)
    }

    // Clear local state
    token.value = ''
    refreshToken.value = ''
    user.value = null

    localStorage.removeItem('token')
    localStorage.removeItem('refreshToken')
    localStorage.removeItem('user')
  }

  async function refreshAccessToken() {
    try {
      const response = await axios.post('/api/v1/auth/refresh', {
        refresh_token: refreshToken.value
      })
      const { access_token } = response.data
      token.value = access_token
      localStorage.setItem('token', access_token)
      return true
    } catch (error) {
      logout()
      return false
    }
  }

  async function fetchUserInfo() {
    try {
      const response = await axios.get('/api/v1/auth/me')
      user.value = response.data
      localStorage.setItem('user', JSON.stringify(response.data))
    } catch (error) {
      console.error('Fetch user info error:', error)
    }
  }

  function hasPermission(permission) {
    if (!user.value) return false
    if (user.value.role === 'super_admin') return true

    const rolePermissions = {
      audit_admin: ['audit:view', 'log:all:read', 'report:all:read'],
      dept_admin: ['user:dept:manage', 'log:dept:read'],
      network_user: ['log:network:read', 'report:own:read', 'ai:manual:run'],
      server_user: ['log:server:read', 'report:own:read', 'ai:manual:run'],
      k8s_user: ['log:k8s:read', 'report:own:read', 'ai:manual:run']
    }

    return rolePermissions[user.value.role]?.includes(permission) || false
  }

  function canAccessLogType(logType) {
    if (!user.value) return false
    if (user.value.role === 'super_admin' || user.value.role === 'audit_admin') return true

    if (user.value.role === 'network_user' && logType === 'network') return true
    if (user.value.role === 'server_user' && logType === 'server') return true
    if (user.value.role === 'k8s_user' && logType === 'k8s') return true

    return false
  }

  return {
    token,
    refreshToken,
    user,
    isLoggedIn,
    userRole,
    userName,
    userEmail,
    login,
    logout,
    refreshAccessToken,
    fetchUserInfo,
    hasPermission,
    canAccessLogType
  }
})