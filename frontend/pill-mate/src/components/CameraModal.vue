<template>
  <div class="camera-modal-overlay" :class="{ 'light': !props.isDark }">
    <div class="camera-modal">
      <!-- Header -->
      <div class="camera-header">
        <h3 class="camera-title">Take Photo</h3>
        <button
          @click="handleClose"
          class="close-btn"
        >
          <svg class="close-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Camera Preview -->
      <div class="camera-preview-container">
        <video
          ref="videoRef"
          autoplay
          muted
          playsinline
          class="camera-preview"
          :class="{ 'hidden': !stream }"
        ></video>
        <div v-if="!stream && !isLoading" class="camera-placeholder">
          <div class="placeholder-content">
            <svg class="placeholder-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <p class="placeholder-text">Camera not available</p>
          </div>
        </div>
        <div v-if="isLoading" class="camera-placeholder">
          <div class="placeholder-content">
            <svg class="placeholder-icon loading" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <p class="placeholder-text">Starting camera...</p>
          </div>
        </div>
      </div>

      <!-- Camera Controls -->
      <div class="camera-controls">
        <button
          @click="capturePhoto"
          :disabled="!stream || isLoading"
          class="capture-btn"
        >
          <svg v-if="isLoading" class="capture-icon loading" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <svg v-else class="capture-icon" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
          </svg>
        </button>
      </div>

      <!-- Error Message -->
      <div v-if="error" class="error-message">
        {{ error }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  isDark: boolean
}>()

const emit = defineEmits<{
  close: []
  capture: [imageData: string]
}>()

const videoRef = ref<HTMLVideoElement>()
const stream = ref<MediaStream | null>(null)
const isLoading = ref(false)
const error = ref('')

const startCamera = async () => {
  try {
    console.log('Starting camera...')
    isLoading.value = true
    error.value = ''
    
    // Try environment camera first (back camera on mobile)
    let constraints = {
      video: {
        facingMode: 'environment',
        width: { ideal: 1280 },
        height: { ideal: 720 }
      }
    }

    try {
      console.log('Trying environment camera...')
      stream.value = await navigator.mediaDevices.getUserMedia(constraints)
      console.log('Environment camera success, stream:', stream.value)
    } catch (envError) {
      console.log('Environment camera failed, trying user camera:', envError)
      // Fallback to user-facing camera
      constraints = {
        video: {
          facingMode: 'user',
          width: { ideal: 1280 },
          height: { ideal: 720 }
        }
      }
      stream.value = await navigator.mediaDevices.getUserMedia(constraints)
      console.log('User camera success, stream:', stream.value)
    }
    
    // Wait for the next tick to ensure video element is rendered
    await new Promise(resolve => setTimeout(resolve, 100))
    
    console.log('Video ref:', videoRef.value)
    if (videoRef.value) {
      console.log('Setting video srcObject...')
      videoRef.value.srcObject = stream.value
      
      // Wait for video to load
      videoRef.value.onloadedmetadata = () => {
        console.log('Camera stream loaded successfully')
      }
      
      videoRef.value.onerror = (e) => {
        console.error('Video element error:', e)
        error.value = 'Failed to display camera preview'
      }
    } else {
      console.error('Video ref is null!')
    }
  } catch (err) {
    console.error('Error accessing camera:', err)
    error.value = 'Unable to access camera. Please check permissions.'
  } finally {
    isLoading.value = false
  }
}

const stopCamera = () => {
  if (stream.value) {
    stream.value.getTracks().forEach(track => track.stop())
    stream.value = null
  }
}

const capturePhoto = () => {
  if (!videoRef.value || !stream.value) return

  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d')
  
  if (!context) return

  canvas.width = videoRef.value.videoWidth
  canvas.height = videoRef.value.videoHeight
  
  context.drawImage(videoRef.value, 0, 0)
  
  const imageData = canvas.toDataURL('image/jpeg', 0.8)
  emit('capture', imageData)
  
  stopCamera()
}

const handleClose = () => {
  stopCamera()
  emit('close')
}

onMounted(() => {
  // Auto-start camera when modal opens
  console.log('Camera modal mounted, starting camera...')
  startCamera()
})

onUnmounted(() => {
  // Stop camera when modal is destroyed
  stopCamera()
})
</script>
