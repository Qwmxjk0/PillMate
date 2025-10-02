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
        
        <!-- Mode Toggle Button - Centered -->
        <div class="header-center">
          <div class="mode-toggle-container">
            <div class="mode-toggle-pill">
              <button 
                @click="setMode(false)"
                class="mode-option"
                :class="{ 'active': !isComparisonMode }"
              >
                Information
              </button>
              <button 
                @click="setMode(true)"
                class="mode-option"
                :class="{ 'active': isComparisonMode }"
              >
                Comparison
              </button>
            </div>
          </div>
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
        <div v-for="message in chatStore.messages" :key="message.id" class="message-wrapper" :class="message.role === 'user' ? 'user-message' : 'assistant-message'">
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
                      <div v-if="message.text" class="message-text-content">
                        <!-- Loading animation for assistant loading messages -->
                        <div v-if="message.role === 'assistant' && message.text === 'loading'" class="loading-container">
                          <div class="loading-dots">
                            <div class="loading-dot"></div>
                            <div class="loading-dot"></div>
                            <div class="loading-dot"></div>
                          </div>
                          <span class="loading-text">Assistant is thinking...</span>
                        </div>
                        <!-- Render markdown for assistant messages, plain text for user messages -->
                        <div v-else-if="message.role === 'assistant'" v-html="renderMarkdown(message.text)"></div>
                        <div v-else>{{ message.text }}</div>
                      </div>
                      
                      <!-- Medicine Buttons (only for assistant messages with suggestion=true) -->
                      <div v-if="message.role === 'assistant' && message.suggestion && message.medicineButtons && message.medicineButtons.length > 0" class="medicine-buttons">
                        <div class="medicine-buttons-header">
                          <h4 class="medicine-buttons-title">Suggested Medicines</h4>
                          <p class="medicine-buttons-subtitle">Tap to add to your medicine list</p>
                        </div>
                        <div class="medicine-buttons-list">
                          <button
                            v-for="medicine in message.medicineButtons"
                            :key="medicine.id"
                            @click="addMedicine(message.id,medicine)"
                            class="medicine-button"
                            :disabled="isAddingMedicine"
                          >
                            <div class="medicine-button-content">
                              <div class="medicine-name">{{ medicine.name }}</div>
                            </div>
                            <div class="medicine-button-icon">
                              <svg class="add-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                              </svg>
                            </div>
                          </button>
                        </div>
                      </div>
                  
                  <!-- Image Content -->
                  <div v-if="message.image" class="message-image">
                    <img :src="message.image" alt="Uploaded image" />
                  </div>
                </div>
                
                <!-- Timestamp -->
                    <div class="message-timestamp" :class="message.role === 'user' ? 'user-timestamp' : 'assistant-timestamp'">
                      {{ chatStore.formatTime(message.timestamp) }}
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
        <!-- Information Mode -->
        <div v-if="!isComparisonMode" class="input-wrapper">
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
                    <!-- Mobile Action Menu -->
                    <div class="mobile-action-menu">
                      <!-- Toggle Button -->
                      <button
                        @click="toggleActionMenu"
                        class="action-toggle-btn"
                        :class="{ 'expanded': showActionMenu }"
                        title="More actions"
                      >
                        <svg v-if="!showActionMenu" class="action-icon" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
                        </svg>
                        <svg v-else class="action-icon" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                        </svg>
                      </button>

                      <!-- Expanded Action Buttons -->
                      <div v-if="showActionMenu" class="action-expanded-menu">
                        <!-- Image Upload Button -->
                        <button
                          @click="triggerImageUpload"
                          class="action-expanded-btn"
                          title="Upload image"
                        >
                          <svg class="action-expanded-icon" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
                          </svg>
                        </button>

                        <!-- Camera Button -->
                        <button
                          @click="openCamera"
                          class="action-expanded-btn"
                          title="Take photo"
                        >
                          <svg class="action-expanded-icon" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"/>
                            <path d="M15 13a3 3 0 11-6 0 3 3 0 016 0z"/>
                          </svg>
                        </button>
                      </div>
                    </div>

                     <!-- Send Button (Always visible) -->
                     <button
                      @click="sendMessage"
                      :disabled="!inputText.trim() && !selectedImage"
                      class="send-btn"
                      title="Send message"
                    >
                      <svg class="send-icon" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                      </svg>
                    </button>
                  </div>
            </div>
          </div>
        </div>

            <!-- Comparison Mode -->
            <div v-else class="comparison-wrapper">
              <div class="comparison-header"
                :style="{ 'margin-bottom': isComparisonCollapsed ? '0' : '1rem' }"
              >
                <h3 class="comparison-title">Compare Drugs</h3>
                <div class="comparison-header-actions">
                  <button 
                    v-if="!isComparisonCollapsed"
                    @click="addComparisonField"
                    :disabled="comparisonTexts.length >= 5"
                    class="add-field-btn"
                    title="Add comparison field (max 5)"
                  >
                    <svg class="add-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                    </svg>
                    Add Field
                  </button>
                  <button 
                    @click="toggleComparisonCollapse"
                    class="collapse-btn"
                    :title="isComparisonCollapsed ? 'Expand comparison form' : 'Collapse comparison form'"
                  >
                    <svg 
                      class="collapse-icon" 
                      :class="{ 'rotated': isComparisonCollapsed }"
                      fill="none" 
                      stroke="currentColor" 
                      viewBox="0 0 24 24"
                    >
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                </div>
              </div>

              <div v-show="!isComparisonCollapsed" class="comparison-content">
                <div class="comparison-fields">
                  <div 
                    v-for="(_, index) in comparisonTexts" 
                    :key="index"
                    class="comparison-field"
                  >
                    <div class="field-header">
                      <span class="field-label">Drug {{ index + 1 }}</span>
                      <button 
                        v-if="comparisonTexts.length >= 3"
                        @click="removeComparisonField(index)"
                        class="remove-field-btn"
                        title="Remove field"
                      >
                        <svg class="remove-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                    <textarea
                      v-model="comparisonTexts[index]"
                      :placeholder="`Enter drug name ${index + 1}...`"
                      class="comparison-input"
                      rows="2"
                    ></textarea>
                  </div>
                </div>

                <div class="comparison-actions">
                  <button
                    @click="sendComparisonMessage"
                    :disabled="!hasValidComparisonInputs"
                    class="comparison-send-btn"
                    title="Send comparison"
                  >
                    <svg class="send-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                    </svg>
                    Compare Drugs
                  </button>
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
        
        <!-- My Drugs Section -->
        <div class="user-drugs-section">
          <div class="user-drugs-header">
            <h4 class="user-drugs-title">My Drugs</h4>
            <span class="user-drugs-count">{{ drugCount }} saved</span>
          </div>
          
          <div v-if="hasUserDrugs" class="user-drugs-list">
            <div 
              v-for="drug in userDrugs" 
              :key="drug.id"
              class="user-drug-item"
            >
              <div class="user-drug-info">
                <div class="user-drug-name">{{ drug.name }}</div>
                <div v-if="drug.created_at" class="user-drug-date">
                  Added {{ formatDate(drug.created_at) }}
                </div>
              </div>
              <button 
                @click="removeDrug(drug.id, drug.name)"
                class="user-drug-remove-btn"
                title="Remove drug"
              >
                <svg class="remove-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
          
          <div v-else class="user-drugs-empty">
            <div class="user-drugs-empty-icon">
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
              </svg>
            </div>
            <p class="user-drugs-empty-text">No drugs saved yet</p>
            <p class="user-drugs-empty-subtext">Add medicines from chat suggestions</p>
          </div>
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

        <!-- Toast Notification -->
        <div v-if="toast.show" class="toast-notification" :class="[`toast-${toast.type}`, { 'light': !isDark }]">
          <div class="toast-content">
            <div class="toast-icon">
              <svg v-if="toast.type === 'success'" class="toast-icon-svg" fill="currentColor" viewBox="0 0 24 24">
                <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
              </svg>
              <svg v-else class="toast-icon-svg" fill="currentColor" viewBox="0 0 24 24">
                <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
              </svg>
            </div>
            <div class="toast-message">{{ toast.message }}</div>
            <button @click="hideToast" class="toast-close">
              <svg class="toast-close-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { marked } from 'marked'
import { useAuthStore } from '../stores/auth'
import { useChatStore } from '../stores/chat'
import { useDrugStore } from '../stores/drug'
import CameraModal from './CameraModal.vue'
import ImageCropModal from './ImageCropModal.vue'
import type { MedicineButton } from '../stores/chat'

const isDark = ref(true)
const inputText = ref('')
const selectedImage = ref('')
const showCamera = ref(false)
const showCropModal = ref(false)
const imageToCrop = ref('')
const fileInput = ref<HTMLInputElement>()
const textInput = ref<HTMLTextAreaElement>()

// Mode toggle state
const isComparisonMode = ref(false)
const comparisonTexts = ref<string[]>(['', ''])
const isComparisonCollapsed = ref(false)

// Stores
const authStore = useAuthStore()
const chatStore = useChatStore()
const drugStore = useDrugStore()

// Local UI state
const showAuthModal = ref(false)
const showUserMenu = ref(false)
const showActionMenu = ref(false)
const isLoginMode = ref(true)
const isAddingMedicine = ref(false)

// Toast notification state
const toast = ref({
  show: false,
  message: '',
  type: 'success' as 'success' | 'error'
})
const authForm = ref({
  email: '',
  password: '',
  confirmPassword: ''
})

// Computed properties from auth store
const isLoggedIn = computed(() => authStore.isLoggedIn)
const userEmail = computed(() => authStore.userEmail)
const isAuthLoading = computed(() => authStore.isLoading)

// Computed properties from drug store
const userDrugs = computed(() => drugStore.drugs)
const hasUserDrugs = computed(() => drugStore.hasDrugs)
const drugCount = computed(() => drugStore.drugCount)

// Theme management
const toggleTheme = () => {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
}

// Mode toggle management
const setMode = (comparison: boolean) => {
  isComparisonMode.value = comparison
  // Reset comparison texts when switching to comparison mode
  if (comparison) {
    comparisonTexts.value = ['', '']
    isComparisonCollapsed.value = false // Reset collapse state
  }
}

// Comparison collapse toggle
const toggleComparisonCollapse = () => {
  isComparisonCollapsed.value = !isComparisonCollapsed.value
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
        // Load chat history for authenticated user
        // await chatStore.loadChatHistory(authStore.user.id)
        // Load user drugs
        await drugStore.loadUserDrugs(authStore.user.id)
      }
})

// Message handling
const sendMessage = async () => {
  if (!inputText.value.trim() && !selectedImage.value) return

  const messageText = inputText.value.trim()
  const messageImage = selectedImage.value
  
  // Clear input immediately
  inputText.value = ''
  selectedImage.value = ''
  
  // Send message via chat store
  await chatStore.sendMessage(
    messageText, 
    messageImage, 
    authStore.user?.id
  )
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
      await drugStore.loadUserDrugs(result.data?.user?.id)
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

  // Action menu functions
  const toggleActionMenu = () => {
    showActionMenu.value = !showActionMenu.value
  }

  // Toast notification functions
  const showToast = (message: string, type: 'success' | 'error' = 'success') => {
    toast.value = {
      show: true,
      message,
      type
    }
    
    // Auto hide after 3 seconds
    setTimeout(() => {
      toast.value.show = false
    }, 3000)
  }

  const hideToast = () => {
    toast.value.show = false
  }

  // Medicine functions
  const addMedicine = async (messageId: string, medicine: MedicineButton) => {
    if (isAddingMedicine.value) return
    
    isAddingMedicine.value = true
    try {

      if (!authStore.user?.id) {
        showToast('Please login to add medicine', 'error')
        return
      }
      
      const result = await drugStore.addDrug(
        authStore.user?.id, 
        medicine.id
      )
      
      if (result.success) {
        showToast(`${result.drug?.name} added to your drug list!`, 'success')
        chatStore.removeMedicineFromUserList(messageId)
      } else {
        showToast(result.error || 'Failed to add medicine', 'error')
      }
    } catch (error) {
      showToast('An error occurred while adding medicine', 'error')
    } finally {
      isAddingMedicine.value = false
    }
  }

  // Drug management functions
  const removeDrug = async (drugId: string, drugName: string) => {
    try {
      const result = await drugStore.removeDrug(drugId)
      
      if (result.success) {
        showToast(`${drugName} removed from your drug list`, 'success')
      } else {
        showToast(result.error || 'Failed to remove drug', 'error')
      }
    } catch (error) {
      showToast('An error occurred while removing drug', 'error')
    }
  }

const handleLogout = async () => {
  await authStore.logout()
  showUserMenu.value = false
  chatStore.clearMessages() // Clear chat history on logout
  drugStore.clearDrugs() // Clear user drugs on logout
}

// Comparison mode functions
const addComparisonField = () => {
  if (comparisonTexts.value.length < 5) {
    comparisonTexts.value.push('')
  }
}

const removeComparisonField = (index: number) => {
  if (comparisonTexts.value.length >= 3) {
    comparisonTexts.value.splice(index, 1)
  }
}

const hasValidComparisonInputs = computed(() => {
  const validTexts = comparisonTexts.value.filter(text => text.trim().length > 0)
  return validTexts.length >= 2
})

const sendComparisonMessage = async () => {
  const validTexts = comparisonTexts.value.filter(text => text.trim().length > 0)
  if (validTexts.length === 0) return

  // Send comparison message via chat store
  await chatStore.sendMessage(
    validTexts, 
    undefined, // No image for comparison
    authStore.user?.id
  )
}

  // Markdown rendering
  const renderMarkdown = (text: string) => {
    return marked(text)
  }

  // Date formatting with Thai timezone support
  const formatDate = (dateInput: Date | string) => {
    let date: Date
    
    // Handle different date input formats
    if (typeof dateInput === 'string') {
      // Support ISO strings with timezone (+00:00, Z, etc.)
      date = new Date(dateInput)
    } else {
      date = dateInput
    }
    
    // Convert to Thai timezone (UTC+7)
    const thaiDate = new Date(date.toLocaleString("en-US", {timeZone: "Asia/Bangkok"}))
    const now = new Date()
    const thaiNow = new Date(now.toLocaleString("en-US", {timeZone: "Asia/Bangkok"}))
    
    const diffTime = Math.abs(thaiNow.getTime() - thaiDate.getTime())
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))
    
    if (diffDays === 1) {
      return 'today'
    } else if (diffDays === 2) {
      return 'yesterday'
    } else if (diffDays <= 7) {
      return `${diffDays - 1} days ago`
    } else {
      // Format date in Thai locale
      return thaiDate.toLocaleDateString('th-TH', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      })
    }
  }

// Utility functions are now handled by the chat store

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
