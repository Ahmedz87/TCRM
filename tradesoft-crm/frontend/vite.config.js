import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Standalone TradeSoft CRM frontend. Dev server proxies /api to the FastAPI backend
// on :8090; production build is emitted to dist/ and served by that same backend.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5190,
    proxy: { '/api': 'http://127.0.0.1:8090' },
  },
  build: { outDir: 'dist' },
})
