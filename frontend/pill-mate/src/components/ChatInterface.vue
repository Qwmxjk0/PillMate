<template>
  <div class="chat-container">
    <!-- Header -->
    <header class="chat-header">
      <div class="header-content">
        <div class="header-left">
          <div class="logo-container">
            <img style="width: 24px; height: 24px;" src="/drugs.png" alt="PillMate Logo" class="logo-image" />
          </div>
          <h1 class="app-title">PillMate</h1>
        </div>
        <div class="header-right">
          <!-- User Authentication Button -->
          <button 
            v-if="!isLoggedIn"
            @click="showAuthModal = true"
            class="auth-btn"
          >
            Login / Register
          </button>
          <button 
            v-else
            @click="handleUserMenu"
            class="user-btn"
            :title="userEmail"
          >
            <svg class="user-icon" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clip-rule="evenodd" />
            </svg>
          </button>
          
          <!-- Theme Toggle -->
          <button 
            @click="toggleTheme"
            class="theme-toggle"
          >
            <svg v-if="isDark" class="theme-icon sun-icon" fill="currentColor" viewBox="0 0 20 20">
              <path fill-rule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" clip-rule="evenodd" />
            </svg>
            <svg v-else class="theme-icon moon-icon" fill="currentColor" viewBox="0 0 20 20">
              <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
            </svg>
          </button>
        </div>
      </div>
    </header>

    <!-- Chat Messages -->
    <main class="chat-main">
      <div class="messages-container">
        <div v-for="message in messages" :key="message.id" class="message-wrapper" :class="message.role === 'user' ? 'user-message' : 'assistant-message'">
          <div class="message-content">
            <div class="message-bubble" :class="message.role === 'user' ? 'user-bubble' : 'assistant-bubble'">
              <!-- Avatar -->
              <div class="message-avatar" :class="message.role === 'user' ? 'user-avatar' : 'assistant-avatar'">
                <span v-if="message.role === 'user'">U</span>
                <span v-else>A</span>
              </div>
              
              <!-- Message Content -->
              <div class="message-text">
                <div class="message-body" :class="message.role === 'user' ? 'user-message-body' : 'assistant-message-body'">
                  <!-- Text Content -->
                  <div v-if="message.text" class="message-text-content">{{ message.text }}</div>
                  
                  <!-- Image Content -->
                  <div v-if="message.image" class="message-image">
                    <img :src="message.image" alt="Uploaded image" />
                  </div>
                </div>
                
                <!-- Timestamp -->
                <div class="message-timestamp" :class="message.role === 'user' ? 'user-timestamp' : 'assistant-timestamp'">
                  {{ formatTime(message.timestamp) }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- Input Area -->
    <div class="input-area">
      <div class="input-container">
        <div class="input-wrapper">
          <!-- Image Preview -->
          <div v-if="selectedImage" class="image-preview">
            <div class="image-preview-container">
              <img :src="selectedImage" alt="Selected image" />
              <button 
                @click="removeImage"
                class="remove-image-btn"
              >
                ×
              </button>
            </div>
          </div>

          <!-- Input Container -->
          <div class="input-content">
            <div class="input-row">
              <!-- Text Input -->
              <div class="text-input-container">
                <textarea
                  v-model="inputText"
                  @keydown="handleKeydown"
                  placeholder="Type your drug name..."
                  class="message-input"
                  rows="1"
                  ref="textInput"
                ></textarea>
              </div>

              <!-- Action Buttons -->
              <div class="action-buttons">
                <!-- Image Upload Button -->
                <button
                  @click="triggerImageUpload"
                  class="action-btn"
                  title="Upload image"
                >
                  <svg class="action-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                </button>

                <!-- Camera Button -->
                <button
                  @click="openCamera"
                  class="action-btn"
                  title="Take photo"
                >
                  <svg class="action-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </button>

                <!-- Send Button -->
                <button
                  @click="sendMessage"
                  :disabled="!inputText.trim() && !selectedImage"
                  class="send-btn"
                  title="Send message"
                >
                  <svg class="send-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Hidden File Input -->
    <input
      ref="fileInput"
      type="file"
      accept="image/*"
      @change="handleFileSelect"
      class="hidden"
    />

    <!-- Camera Modal -->
    <CameraModal
      v-if="showCamera"
      :is-dark="isDark"
      @close="closeCamera"
      @capture="handleCameraCapture"
    />

    <!-- Image Crop Modal -->
    <ImageCropModal
      v-if="showCropModal"
      :image="imageToCrop"
      :is-dark="isDark"
      @close="closeCropModal"
      @crop="handleImageCrop"
    />

    <!-- Authentication Modal -->
    <div v-if="showAuthModal" class="auth-modal-overlay" @click="closeAuthModal" :class="{ 'light': !isDark }">
      <div class="auth-modal" @click.stop>
        <div class="auth-header">
          <h3 class="auth-title">{{ isLoginMode ? 'Login' : 'Register' }}</h3>
          <button @click="closeAuthModal" class="close-btn">
            <svg class="close-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        
        <form @submit.prevent="handleAuth" class="auth-form">
          <div class="form-group">
            <label for="email">Email</label>
            <input
              id="email"
              v-model="authForm.email"
              type="email"
              required
              placeholder="Enter your email"
              class="form-input"
            />
          </div>
          
          <div class="form-group">
            <label for="password">Password</label>
            <input
              id="password"
              v-model="authForm.password"
              type="password"
              required
              placeholder="Enter your password"
              class="form-input"
            />
          </div>
          
          <div v-if="!isLoginMode" class="form-group">
            <label for="confirmPassword">Confirm Password</label>
            <input
              id="confirmPassword"
              v-model="authForm.confirmPassword"
              type="password"
              required
              placeholder="Confirm your password"
              class="form-input"
            />
          </div>
          
          <!-- Error Message -->
          <div v-if="authStore.error" class="auth-error">
            {{ authStore.error }}
          </div>
          
          <div class="auth-actions">
            <button type="submit" class="auth-submit-btn" :disabled="isAuthLoading">
              {{ isAuthLoading ? 'Processing...' : (isLoginMode ? 'Login' : 'Register') }}
            </button>
            
            <button type="button" @click="toggleAuthMode" class="auth-toggle-btn">
              {{ isLoginMode ? 'Need an account? Register' : 'Have an account? Login' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- User Menu Dropdown -->
    <div v-if="showUserMenu" class="user-menu-overlay" @click="closeUserMenu" :class="{ 'light': !isDark }">
      <div class="user-menu" @click.stop>
        <div class="user-info">
          <div class="user-email">{{ userEmail }}</div>
        </div>
        <div class="user-menu-actions">
          <button @click="handleLogout" class="logout-btn">
            <svg class="logout-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Logout
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useAuthStore } from '../stores/auth'
import CameraModal from './CameraModal.vue'
import ImageCropModal from './ImageCropModal.vue'

interface Message {
  id: string
  role: 'user' | 'assistant'
  text?: string
  image?: string
  timestamp: Date
}

const isDark = ref(true)
const inputText = ref('')
const selectedImage = ref('')
const messages = ref<Message[]>([])
const showCamera = ref(false)
const showCropModal = ref(false)
const imageToCrop = ref('')
const fileInput = ref<HTMLInputElement>()
const textInput = ref<HTMLTextAreaElement>()

// Auth store
const authStore = useAuthStore()

// Local UI state
const showAuthModal = ref(false)
const showUserMenu = ref(false)
const isLoginMode = ref(true)
const authForm = ref({
  email: '',
  password: '',
  confirmPassword: ''
})

// Computed properties from auth store
const isLoggedIn = computed(() => authStore.isLoggedIn)
const userEmail = computed(() => authStore.userEmail)
const isAuthLoading = computed(() => authStore.isLoading)

// Theme management
const toggleTheme = () => {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
}

// Initialize theme and auth
onMounted(async () => {
  const savedTheme = localStorage.getItem('theme')
  // Default to dark theme, but respect saved preference
  isDark.value = savedTheme ? savedTheme === 'dark' : true
  document.documentElement.classList.toggle('dark', isDark.value)
  
  // Initialize auth store
  authStore.initializeAuth()
  
  // Check if user is already authenticated
  if (authStore.user) {
    await authStore.checkAuth()
  }
  
  // TODO: Load chat history from API
  // - Fetch previous messages from backend
  // - Populate messages array with historical data
  // - Handle loading states and error cases
  // - Implement pagination for large chat histories
})

// Message handling
const sendMessage = async () => {
  if (!inputText.value.trim() && !selectedImage.value) return

  const userMessage: Message = {
    id: Date.now().toString(),
    role: 'user',
    text: inputText.value.trim(),
    image: selectedImage.value,
    timestamp: new Date()
  }

  messages.value.push(userMessage)
  
  // Clear input
  inputText.value = ''
  selectedImage.value = ''
  
  // Simulate AI response
  setTimeout(() => {
    const aiMessage: Message = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      text: 'I received your message' + (userMessage.image ? ' with an image' : '') + '. How can I help you further?',
      timestamp: new Date()
    }
    messages.value.push(aiMessage)
  }, 1000)

  // TODO: Integrate with API
  // - Send message to backend API endpoint
  // - Handle image upload to cloud storage
  // - Process message with AI/ML service
  // - Receive and display AI response
  // - Handle API errors and loading states
  // - Implement retry logic for failed requests
}

// Input handling
const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

// Image handling
const triggerImageUpload = () => {
  fileInput.value?.click()
}

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) {
    const reader = new FileReader()
    reader.onload = (e) => {
      const result = e.target?.result as string
      imageToCrop.value = result
      showCropModal.value = true
    }
    reader.readAsDataURL(file)
  }
}

const openCamera = () => {
  showCamera.value = true
}

const closeCamera = () => {
  showCamera.value = false
}

const handleCameraCapture = (imageData: string) => {
  imageToCrop.value = imageData
  showCropModal.value = true
  showCamera.value = false
}

const closeCropModal = () => {
  showCropModal.value = false
  imageToCrop.value = ''
}

const handleImageCrop = (croppedImage: string) => {
  selectedImage.value = croppedImage
  showCropModal.value = false
  imageToCrop.value = ''
  sendMessage()
}

const removeImage = () => {
  selectedImage.value = ''
}

// Authentication functions
const toggleAuthMode = () => {
  isLoginMode.value = !isLoginMode.value
  authForm.value = { email: '', password: '', confirmPassword: '' }
}

const closeAuthModal = () => {
  showAuthModal.value = false
  authForm.value = { email: '', password: '', confirmPassword: '' }
}

const handleAuth = async () => {
  try {
    let result
    
    if (isLoginMode.value) {
      result = await authStore.login(authForm.value.email, authForm.value.password)
    } else {
      result = await authStore.register(
        authForm.value.email, 
        authForm.value.password, 
        authForm.value.confirmPassword
      )
    }
    
    if (result.success) {
      showAuthModal.value = false
      authForm.value = { email: '', password: '', confirmPassword: '' }
      authStore.clearError()
    } else {
      // Error is already set in the store
      console.error('Auth error:', result.error)
    }
  } catch (error) {
    console.error('Unexpected auth error:', error)
  }
}

const handleUserMenu = () => {
  showUserMenu.value = !showUserMenu.value
}

const closeUserMenu = () => {
  showUserMenu.value = false
}

const handleLogout = async () => {
  await authStore.logout()
  showUserMenu.value = false
  messages.value = [] // Clear chat history on logout
}

// Utility functions
const formatTime = (date: Date) => {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

// Auto-resize textarea
onMounted(() => {
  if (textInput.value) {
    textInput.value.addEventListener('input', () => {
      textInput.value!.style.height = 'auto'
      textInput.value!.style.height = textInput.value!.scrollHeight + 'px'
    })
  }
})
</script>
