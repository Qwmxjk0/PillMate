<template>
  <div class="crop-modal-overlay" :class="{ 'light': !props.isDark }">
    <div class="crop-modal">
      <!-- Header -->
      <div class="crop-header">
        <h3 class="crop-title">Crop Image</h3>
        <button
          @click="$emit('close')"
          class="close-btn"
        >
          <svg class="close-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Image Container with Crop Area -->
      <div class="crop-preview-container">
        <div class="crop-image-wrapper" ref="cropContainer">
          <img
            ref="imageRef"
            :src="image"
            alt="Image to crop"
            class="crop-image"
            @load="initializeCropper"
          />
          <!-- Crop Selection Area -->
          <div 
            v-if="cropArea"
            class="crop-selection"
            :style="cropAreaStyle"
            @mousedown="startDrag"
          >
            <div class="crop-handles">
              <div class="crop-handle top-left" @mousedown="startResize('nw')"></div>
              <div class="crop-handle top-right" @mousedown="startResize('ne')"></div>
              <div class="crop-handle bottom-left" @mousedown="startResize('sw')"></div>
              <div class="crop-handle bottom-right" @mousedown="startResize('se')"></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Crop Controls -->
      <div class="crop-controls">
        <!-- Rotation Controls -->
        <!-- <div class="rotation-controls">
          <button
            @click="rotateLeft"
            class="control-btn secondary"
            title="Rotate left"
          >
            <svg class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>

          <button
            @click="rotateRight"
            class="control-btn secondary"
            title="Rotate right"
          >
            <svg class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>

          <button
            @click="resetCrop"
            class="control-btn secondary"
            title="Reset crop"
          >
            <svg class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div> -->

        <!-- Aspect Ratio Options -->
        <!-- <div class="aspect-ratio-controls">
          <span class="aspect-label">Aspect Ratio:</span>
          <div class="aspect-buttons">
            <button
              v-for="ratio in aspectRatios"
              :key="ratio.value"
              @click="setAspectRatio(ratio.value)"
              :class="[
                'aspect-btn',
                currentAspectRatio === ratio.value ? 'active' : ''
              ]"
            >
              {{ ratio.label }}
            </button>
          </div>
        </div> -->

        <!-- Action Buttons -->
        <div class="action-buttons">
          <button
            @click="$emit('close')"
            class="control-btn secondary"
          >
            Cancel
          </button>
          <button
            @click="cropImage"
            class="crop-btn"
          >
            Crop & Use
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'

interface AspectRatio {
  value: number | null
  label: string
}

interface CropArea {
  x: number
  y: number
  width: number
  height: number
}

const props = defineProps<{
  image: string
  isDark: boolean
}>()

const emit = defineEmits<{
  close: []
  crop: [croppedImage: string]
}>()

const imageRef = ref<HTMLImageElement>()
const cropContainer = ref<HTMLDivElement>()
const cropArea = ref<CropArea | null>(null)
const currentAspectRatio = ref<number | null>(null)
const isDragging = ref(false)
const isResizing = ref(false)
const resizeDirection = ref<string>('')
const dragStart = ref({ x: 0, y: 0 })
const imageData = ref<any>(null)

const aspectRatios: AspectRatio[] = [
  { value: null, label: 'Free' },
  { value: 1, label: '1:1' },
  { value: 4/3, label: '4:3' },
  { value: 16/9, label: '16:9' },
  { value: 3/2, label: '3:2' }
]

const cropAreaStyle = computed(() => {
  if (!cropArea.value) return {}
  return {
    left: `${cropArea.value.x}px`,
    top: `${cropArea.value.y}px`,
    width: `${cropArea.value.width}px`,
    height: `${cropArea.value.height}px`
  }
})

const initializeCropper = () => {
  if (!imageRef.value || !cropContainer.value) return

  const img = imageRef.value
  const container = cropContainer.value
  
  // Wait for image to be fully loaded and positioned
  setTimeout(() => {
    const containerRect = container.getBoundingClientRect()
    const imgRect = img.getBoundingClientRect()
    
    // Calculate the actual image position within the container
    const imgOffsetX = (containerRect.width - imgRect.width) / 2
    const imgOffsetY = (containerRect.height - imgRect.height) / 2
    const imgLeft = Math.max(0, imgOffsetX)
    const imgTop = Math.max(0, imgOffsetY)
    const imgRight = Math.min(containerRect.width, imgOffsetX + imgRect.width)
    const imgBottom = Math.min(containerRect.height, imgOffsetY + imgRect.height)
    
    // Set up initial crop area to cover the full image, constrained to image bounds
    cropArea.value = {
      x: imgLeft,
      y: imgTop,
      width: imgRight - imgLeft,
      height: imgBottom - imgTop
    }

    // Store image data for cropping
    imageData.value = {
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight,
      displayWidth: imgRect.width,
      displayHeight: imgRect.height,
      containerWidth: containerRect.width,
      containerHeight: containerRect.height
    }
  }, 100) // Small delay to ensure proper positioning
}

const startDrag = (event: MouseEvent) => {
  if (isResizing.value) return
  
  isDragging.value = true
  dragStart.value = {
    x: event.clientX - (cropArea.value?.x || 0),
    y: event.clientY - (cropArea.value?.y || 0)
  }
  
  document.addEventListener('mousemove', handleDrag)
  document.addEventListener('mouseup', stopDrag)
  event.preventDefault()
}

const handleDrag = (event: MouseEvent) => {
  if (!isDragging.value || !cropArea.value || !cropContainer.value || !imageRef.value) return
  
  const containerRect = cropContainer.value.getBoundingClientRect()
  const imgRect = imageRef.value.getBoundingClientRect()
  const relativeX = event.clientX - containerRect.left
  const relativeY = event.clientY - containerRect.top
  
  const newX = relativeX - dragStart.value.x
  const newY = relativeY - dragStart.value.y
  
  // Calculate image bounds within container
  const imgOffsetX = (containerRect.width - imgRect.width) / 2
  const imgOffsetY = (containerRect.height - imgRect.height) / 2
  const imgLeft = Math.max(0, imgOffsetX)
  const imgTop = Math.max(0, imgOffsetY)
  const imgRight = Math.min(containerRect.width, imgOffsetX + imgRect.width)
  const imgBottom = Math.min(containerRect.height, imgOffsetY + imgRect.height)
  
  // Constrain to image bounds
  const minX = imgLeft
  const maxX = imgRight - cropArea.value.width
  const minY = imgTop
  const maxY = imgBottom - cropArea.value.height
  
  cropArea.value.x = Math.max(minX, Math.min(newX, maxX))
  cropArea.value.y = Math.max(minY, Math.min(newY, maxY))
}

const stopDrag = () => {
  isDragging.value = false
  document.removeEventListener('mousemove', handleDrag)
  document.removeEventListener('mouseup', stopDrag)
}

const startResize = (direction: string) => {
  isResizing.value = true
  resizeDirection.value = direction
  document.addEventListener('mousemove', handleResize)
  document.addEventListener('mouseup', stopResize)
}

const handleResize = (event: MouseEvent) => {
  if (!isResizing.value || !cropArea.value || !cropContainer.value || !imageRef.value) return
  
  const containerRect = cropContainer.value.getBoundingClientRect()
  const imgRect = imageRef.value.getBoundingClientRect()
  const relativeX = event.clientX - containerRect.left
  const relativeY = event.clientY - containerRect.top
  
  // Calculate image bounds within container
  const imgOffsetX = (containerRect.width - imgRect.width) / 2
  const imgOffsetY = (containerRect.height - imgRect.height) / 2
  const imgLeft = Math.max(0, imgOffsetX)
  const imgTop = Math.max(0, imgOffsetY)
  const imgRight = Math.min(containerRect.width, imgOffsetX + imgRect.width)
  const imgBottom = Math.min(containerRect.height, imgOffsetY + imgRect.height)
  
  const direction = resizeDirection.value
  let newX = cropArea.value.x
  let newY = cropArea.value.y
  let newWidth = cropArea.value.width
  let newHeight = cropArea.value.height
  
  if (direction.includes('e')) {
    newWidth = Math.max(50, Math.min(relativeX - cropArea.value.x, imgRight - cropArea.value.x))
  }
  if (direction.includes('w')) {
    newX = Math.max(imgLeft, Math.min(cropArea.value.x + cropArea.value.width - 50, relativeX))
    newWidth = cropArea.value.x + cropArea.value.width - newX
  }
  if (direction.includes('s')) {
    newHeight = Math.max(50, Math.min(relativeY - cropArea.value.y, imgBottom - cropArea.value.y))
  }
  if (direction.includes('n')) {
    newY = Math.max(imgTop, Math.min(cropArea.value.y + cropArea.value.height - 50, relativeY))
    newHeight = cropArea.value.y + cropArea.value.height - newY
  }
  
  // Apply aspect ratio constraint
  if (currentAspectRatio.value && currentAspectRatio.value > 0) {
    const ratio = currentAspectRatio.value
    if (direction.includes('e') || direction.includes('w')) {
      newHeight = newWidth / ratio
    } else {
      newWidth = newHeight * ratio
    }
  }
  
  // Constrain to image bounds
  newX = Math.max(imgLeft, Math.min(newX, imgRight - newWidth))
  newY = Math.max(imgTop, Math.min(newY, imgBottom - newHeight))
  newWidth = Math.min(newWidth, imgRight - newX)
  newHeight = Math.min(newHeight, imgBottom - newY)
  
  cropArea.value = { x: newX, y: newY, width: newWidth, height: newHeight }
}

const stopResize = () => {
  isResizing.value = false
  resizeDirection.value = ''
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
}

const rotateLeft = () => {
  // Simple rotation - in a real app you'd use a proper image manipulation library
  console.log('Rotate left')
}

const rotateRight = () => {
  // Simple rotation - in a real app you'd use a proper image manipulation library
  console.log('Rotate right')
}

const resetCrop = () => {
  initializeCropper()
}

const setAspectRatio = (ratio: number | null) => {
  currentAspectRatio.value = ratio
  if (cropArea.value && ratio && ratio > 0 && imageRef.value && cropContainer.value) {
    const containerRect = cropContainer.value.getBoundingClientRect()
    const imgRect = imageRef.value.getBoundingClientRect()
    
    // Calculate image bounds within container
    const imgOffsetX = (containerRect.width - imgRect.width) / 2
    const imgOffsetY = (containerRect.height - imgRect.height) / 2
    const imgLeft = Math.max(0, imgOffsetX)
    const imgTop = Math.max(0, imgOffsetY)
    const imgRight = Math.min(containerRect.width, imgOffsetX + imgRect.width)
    const imgBottom = Math.min(containerRect.height, imgOffsetY + imgRect.height)
    
    // Adjust crop area to maintain aspect ratio while staying within image bounds
    const currentRatio = cropArea.value.width / cropArea.value.height
    let newWidth = cropArea.value.width
    let newHeight = cropArea.value.height
    
    if (currentRatio > ratio) {
      newHeight = cropArea.value.width / ratio
    } else {
      newWidth = cropArea.value.height * ratio
    }
    
    // Constrain to image bounds
    newWidth = Math.min(newWidth, imgRight - cropArea.value.x)
    newHeight = Math.min(newHeight, imgBottom - cropArea.value.y)
    
    // If the new size would exceed bounds, adjust from the opposite direction
    if (newWidth > imgRight - cropArea.value.x) {
      newWidth = imgRight - cropArea.value.x
      newHeight = newWidth / ratio
    }
    if (newHeight > imgBottom - cropArea.value.y) {
      newHeight = imgBottom - cropArea.value.y
      newWidth = newHeight * ratio
    }
    
    cropArea.value.width = newWidth
    cropArea.value.height = newHeight
  }
}

const cropImage = () => {
  if (!cropArea.value || !imageData.value || !imageRef.value) return
  
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  
  if (!ctx) return
  
  // Get the actual image position within the container
  const imgRect = imageRef.value.getBoundingClientRect()
  const containerRect = cropContainer.value?.getBoundingClientRect()
  
  if (!containerRect) return
  
  // Calculate the image offset within the container
  const imgOffsetX = (containerRect.width - imgRect.width) / 2
  const imgOffsetY = (containerRect.height - imgRect.height) / 2
  
  // Calculate the crop area relative to the image
  const cropX = Math.max(0, cropArea.value.x - imgOffsetX)
  const cropY = Math.max(0, cropArea.value.y - imgOffsetY)
  const cropWidth = Math.min(cropArea.value.width, imgRect.width - cropX)
  const cropHeight = Math.min(cropArea.value.height, imgRect.height - cropY)
  
  // Calculate scale factors
  const scaleX = imageData.value.naturalWidth / imageData.value.displayWidth
  const scaleY = imageData.value.naturalHeight / imageData.value.displayHeight
  
  // Set canvas size to crop area
  canvas.width = cropWidth * scaleX
  canvas.height = cropHeight * scaleY
  
  // Draw cropped portion
  ctx.drawImage(
    imageRef.value,
    cropX * scaleX,
    cropY * scaleY,
    cropWidth * scaleX,
    cropHeight * scaleY,
    0,
    0,
    canvas.width,
    canvas.height
  )
  
  const croppedImage = canvas.toDataURL('image/jpeg', 0.8)
  emit('crop', croppedImage)
}

onMounted(() => {
  // Wait for image to load completely
  if (imageRef.value) {
    if (imageRef.value.complete) {
      initializeCropper()
    } else {
      imageRef.value.addEventListener('load', initializeCropper)
    }
  }
})

onUnmounted(() => {
  document.removeEventListener('mousemove', handleDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
  
  // Clean up image load event listener
  if (imageRef.value) {
    imageRef.value.removeEventListener('load', initializeCropper)
  }
})
</script>
