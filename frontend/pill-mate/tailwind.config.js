/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'pill-primary': '#8B5CF6',
        'pill-secondary': '#A78BFA',
        'pill-accent': '#C4B5FD',
        'pill-dark': '#1F2937',
        'pill-darker': '#111827',
        'pill-light': '#F9FAFB',
        'pill-lighter': '#FFFFFF',
      },
      borderRadius: {
        'pill': '2rem',
      }
    },
  },
  plugins: [],
}
