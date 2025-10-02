import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

// Configure axios defaults
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:3001'
axios.defaults.baseURL = `${API_BASE_URL}`
axios.defaults.headers.common['Content-Type'] = 'application/json'

export const useAuthStore = defineStore('auth', () => {
  // State
  const user = ref<{
    id: string
    email: string
    name?: string
  } | null>(null)
  
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Getters
  const isLoggedIn = computed(() => !!user.value)
  const userEmail = computed(() => user.value?.email || '')

  const login = async (email: string, password: string) => {
    try {
      isLoading.value = true
      error.value = null

      const response = await axios.post('/users/login', {
        email,
        password
      })

      const { user: userData } = response.data
      
      // Store token and user data
      user.value = userData
      localStorage.setItem('user_data', JSON.stringify(userData))

      return { success: true, data: response.data }
    } catch (err: any) {
      error.value = err.response?.data?.message || 'Login failed'
      return { success: false, error: error.value }
    } finally {
      isLoading.value = false
    }
  }

  const register = async (email: string, password: string, confirmPassword: string) => {
    try {
      isLoading.value = true
      error.value = null

      // Validate passwords match
      if (password !== confirmPassword) {
        error.value = 'Passwords do not match'
        return { success: false, error: error.value }
      }

      const response = await axios.post('/users', {
        email,
        password,
        confirm_password: confirmPassword
      })

      const { user: userData } = response.data
      
      // Store token and user data
      user.value = userData
      localStorage.setItem('user_data', JSON.stringify(userData))

      return { success: true, data: response.data }
    } catch (err: any) {
      error.value = err.response?.data?.message || 'Registration failed'
      return { success: false, error: error.value }
    } finally {
      isLoading.value = false
    }
  }

  const logout = async () => {
    // Clear local state regardless of API call result
    user.value = null
    localStorage.removeItem('user_data')
  }

  const checkAuth = async () => {
    try {
      if (!user.value) return false
      return true
    } catch (err) {
      // Token is invalid, clear auth state
      logout()
      return false
    }
  }

  const initializeAuth = () => {
    const storedUser = localStorage.getItem('user_data')

    if (storedUser) {
      user.value = JSON.parse(storedUser)
    }
  }

  const clearError = () => {
    error.value = null
  }

  return {
    // State
    user,
    isLoading,
    error,
    
    // Getters
    isLoggedIn,
    userEmail,
    
    // Actions
    login,
    register,
    logout,
    checkAuth,
    initializeAuth,
    clearError
  }
})
