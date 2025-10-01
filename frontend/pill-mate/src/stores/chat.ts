import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { v4 as UUIDv4 } from 'uuid'
import axios from 'axios'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  text?: string
  image?: string
  timestamp: Date
}

export const useChatStore = defineStore('chat', () => {
  // State
  const messages = ref<Message[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Getters
  const hasMessages = computed(() => messages.value.length > 0)
  const lastMessage = computed(() => messages.value[messages.value.length - 1])

  // Actions
  const addMessage = (message: Omit<Message, 'id' | 'timestamp'>) => {
    const newMessage: Message = {
      ...message,
      id: UUIDv4(),
      timestamp: new Date()
    }
    messages.value.push(newMessage)
    return newMessage
  }

  const sendMessage = async (text: string | string[], image?: string, userId?: string) => {
    try {
      isLoading.value = true
      error.value = null

      // Add user message
      const userMessage = addMessage({
        role: 'user',
        text: text instanceof Array ? `Compare: ${text.join(', ')}` : text.trim(),
        image
      })

      // Add temporary loading message for assistant
      const loadingMessage = addMessage({
        role: 'assistant',
        text: 'loading' // Special identifier for loading state
      })

      // Prepare request data based on whether image is present
      let requestData: any
      let config: any = {}

      if (image) {
        // If image is provided, send as form-data without drug_name
        const response = await fetch(image)
        const blob = await response.blob()
        const file = new File([blob], 'image.jpg', { type: 'image/jpeg' })
        
        const formData = new FormData()
        formData.append('user_id', userId || '')
        formData.append('file', file)
        
        requestData = formData
        config.headers = {
          'Content-Type': 'multipart/form-data'
        }
      } else {
        // If text only, send as JSON with drug_name
        requestData = {
          user_id: userId,
          drug_name: text instanceof Array ? text : [text.trim()],
        }
        config.headers = {
          'Content-Type': 'application/json'
        }
      }

      // Call API to analyze the message
      const response = await axios.post('/analyze', requestData, config)

      const { llm_response } = response.data

      // Remove loading message and add actual AI response
      const loadingIndex = messages.value.findIndex(msg => msg.id === loadingMessage.id)
      

      if (loadingIndex !== -1) {
        messages.value.splice(loadingIndex, 1)
      }

      const aiMessage = addMessage({
        role: 'assistant',
        text: llm_response
      })

      return { success: true, userMessage, aiMessage }
    } catch (err: any) {
      error.value = err.response?.data?.message || 'Failed to send message'
      
      // Add error message
      const errorMessage = addMessage({
        role: 'assistant',
        text: 'Sorry, I encountered an error processing your message. Please try again.'
      })

      return { success: false, error: error.value, errorMessage }
    } finally {
      isLoading.value = false
    }
  }

  const loadChatHistory = async (userId?: string) => {
    try {
      isLoading.value = true
      error.value = null

      const response = await axios.get('/history', {
        params: { user_id: userId }
      })

      // Clear existing messages and load history
      messages.value = response.data.messages.map((msg: any) => ({
        id: msg.id,
        role: msg.role,
        text: msg.text,
        image: msg.image,
        timestamp: new Date(msg.timestamp)
      }))

      return { success: true }
    } catch (err: any) {
      error.value = err.response?.data?.message || 'Failed to load chat history'
      return { success: false, error: error.value }
    } finally {
      isLoading.value = false
    }
  }

  const clearMessages = () => {
    messages.value = []
  }

  const clearError = () => {
    error.value = null
  }

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  return {
    // State
    messages,
    isLoading,
    error,
    
    // Getters
    hasMessages,
    lastMessage,
    
    // Actions
    addMessage,
    sendMessage,
    loadChatHistory,
    clearMessages,
    clearError,
    formatTime
  }
})
