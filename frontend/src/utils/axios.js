import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'

const instance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor
instance.interceptors.request.use(
  (config) => {
    const authStore = useAuthStore()
    if (authStore.token) {
      config.headers.Authorization = `Bearer ${authStore.token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
instance.interceptors.response.use(
  (response) => {
    return response.data
  },
  async (error) => {
    const authStore = useAuthStore()

    if (error.response) {
      const status = error.response.status
      const message = error.response.data?.detail || error.response.data?.error || 'Request failed'

      if (status === 401) {
        // Token expired, try to refresh
        if (authStore.refreshToken) {
          const refreshed = await authStore.refreshAccessToken()
          if (refreshed) {
            // Retry original request
            error.config.headers.Authorization = `Bearer ${authStore.token}`
            return instance.request(error.config)
          }
        }
        // Refresh failed, logout
        authStore.logout()
        window.location.href = '/login'
        ElMessage.error('Session expired, please login again')
      } else if (status === 403) {
        ElMessage.error('Permission denied')
      } else if (status === 404) {
        ElMessage.error('Resource not found')
      } else if (status === 429) {
        ElMessage.error('Too many requests, please wait')
      } else if (status >= 500) {
        ElMessage.error('Server error, please try again later')
      } else {
        ElMessage.error(message)
      }
    } else if (error.request) {
      ElMessage.error('Network error, please check connection')
    } else {
      ElMessage.error(error.message || 'Unknown error')
    }

    return Promise.reject(error)
  }
)

export default instance