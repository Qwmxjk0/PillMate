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
  suggestion?: boolean
  medicineButtons?: MedicineButton[]
}

export interface MedicineButton {
  id: string
  name: string
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

    try {
        // Prepare request data based on whether image is present
        let requestData: any
        let config: any = {}

        requestData = {
            user_id: userId
        }

        if (image) {
        requestData.img_base64 = image
        } else {
        requestData.drug_name = text instanceof Array ? text : [text.trim()]
        }

        config.headers = {
        'Content-Type': 'application/json'
        }

        // Call API to analyze the message
        const response = await axios.post('/analyze', requestData, config)

        const { llm_response, suggestion, drug_found } = response.data

        // Remove loading message and add actual AI response
        const loadingIndex = messages.value.findIndex(msg => msg.id === loadingMessage.id)
        

        if (loadingIndex !== -1) {
            messages.value.splice(loadingIndex, 1)
        }

        
        let resultMessage: Message = {
            id: UUIDv4(),
            timestamp: new Date(),
            role: 'assistant',
            text: llm_response,
            suggestion: suggestion,
        }

        if (suggestion) {
            resultMessage.medicineButtons = [{
                id: drug_found[0],
                name: text instanceof Array ? text.join(', ') : text
            }]
        }

        const aiMessage = addMessage(resultMessage)

        return { success: true, userMessage, aiMessage }
    } catch (err: any) {
        error.value = err.response?.data?.message || 'Failed to send message'

        const loadingIndex = messages.value.findIndex(msg => msg.id === loadingMessage.id)
        

        if (loadingIndex !== -1) {
        messages.value.splice(loadingIndex, 1)
        }
        
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

//   const loadChatHistory = async (userId?: string) => {
//     try {
//       isLoading.value = true
//       error.value = null

//       const response = await axios.get('/history', {
//         params: { user_id: userId }
//       })

//       // Clear existing messages and load history
//       messages.value = response.data.messages.map((msg: any) => ({
//         id: msg.id,
//         role: msg.role,
//         text: msg.text,
//         image: msg.image,
//         timestamp: new Date(msg.timestamp)
//       }))

//       return { success: true }
//     } catch (err: any) {
//       error.value = err.response?.data?.message || 'Failed to load chat history'
//       return { success: false, error: error.value }
//     } finally {
//       isLoading.value = false
//     }
//   }

  const clearMessages = () => {
    messages.value = []
  }

  const clearError = () => {
    error.value = null
  }

  const formatTime = (date: Date | string) => {
    let dateObj: Date
    
    // Handle different date input formats
    if (typeof date === 'string') {
      // Support ISO strings with timezone (+00:00, Z, etc.)
      dateObj = new Date(date)
    } else {
      dateObj = date
    }
    
    // Convert to Thai timezone (UTC+7) and format time
    const thaiDate = new Date(dateObj.toLocaleString("en-US", {timeZone: "Asia/Bangkok"}))
    return thaiDate.toLocaleTimeString('th-TH', { 
      hour: '2-digit', 
      minute: '2-digit',
      hour12: false
    })
  }

  // TODO: Integrate with API to add medicine to user's medicine list
//   const addMedicineToUserList = async (medicine: MedicineButton, _userId?: string) => {
//     try {
//       // TODO: Replace with actual API call
//       // const response = await axios.post('/user/medicines', {
//       //   user_id: userId,
//       //   medicine_id: medicine.id,
//       //   name: medicine.name
//       // })
      
//       // Simulate API call for now
//       await new Promise(resolve => setTimeout(resolve, 1000))
      
//       // TODO: Update user's medicine list in UI
      
//       return { 
//         success: true, 
//         message: `${medicine.name} has been added to your medicine list!` 
//       }
//     } catch (error) {
//       return { 
//         success: false, 
//         error: 'Failed to add medicine to your list. Please try again.' 
//       }
//     }
//   }

  const removeMedicineFromUserList = (messageId: string) => {
    const index = messages.value.findIndex(msg => msg.id == messageId)
    if (index !== -1) {
        messages.value[index].medicineButtons = undefined
    }
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
    // loadChatHistory,
    clearMessages,
    clearError,
    formatTime,
    removeMedicineFromUserList
  }
})
