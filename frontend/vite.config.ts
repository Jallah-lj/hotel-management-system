import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const proxy = {
  '/api': {
    target: process.env.VITE_API_PROXY ?? 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
  '/health': {
    target: process.env.VITE_API_PROXY ?? 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    proxy,
  },
  // Keep the exact same API proxy when the built frontend is served through
  // `vite preview`; otherwise a production-style preview would serve the UI
  // but send /api requests to the static server instead of the backend.
  preview: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy,
  },
})
