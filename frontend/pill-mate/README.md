# PillMate Frontend

A ChatGPT-like interface for PillMate with image upload, camera capture, and image cropping functionality.

## Features

- 🤖 **ChatGPT-like Interface**: Clean, modern chat interface with message bubbles
- 📱 **Responsive Design**: Works perfectly on desktop and mobile devices
- 🌙 **Dark/Light Theme**: Toggle between dark and light themes with system preference detection
- 💊 **Pill Theme**: Custom purple pill-themed design with rounded corners and gradients
- 📝 **Text Input**: Multi-line text input with auto-resize and keyboard shortcuts
- 📷 **Camera Capture**: Take photos directly from your device camera
- 🖼️ **Image Upload**: Upload images from your device
- ✂️ **Image Cropping**: Crop and rotate images before sending
- 🎨 **Tailwind CSS**: Modern styling with Tailwind CSS and custom components

## Tech Stack

- **Vue 3** with Composition API and TypeScript
- **Vite** for fast development and building
- **Tailwind CSS** for styling
- **Custom Components** for camera and image cropping

## Project Setup

```sh
npm install
```

### Development

```sh
npm run dev
```

### Build for Production

```sh
npm run build
```

### Preview Production Build

```sh
npm run preview
```

## Usage

1. **Text Messages**: Type your message and press Enter to send
2. **Image Upload**: Click the image icon to upload from device
3. **Camera Capture**: Click the camera icon to take a photo
4. **Image Cropping**: After selecting/capturing an image, crop it to your preference
5. **Theme Toggle**: Click the sun/moon icon to switch themes

## Components

- `ChatInterface.vue` - Main chat interface
- `CameraModal.vue` - Camera capture modal
- `ImageCropModal.vue` - Image cropping modal

## Customization

The app uses a custom pill theme with purple colors. You can customize the colors in `tailwind.config.js` and `src/style.css`.
