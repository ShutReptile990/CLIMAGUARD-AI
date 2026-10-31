import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
export default defineConfig(({ mode }) => {
  const apiBase = loadEnv(mode, process.cwd(), 'VITE_').VITE_API_BASE_URL?.trim()
  return {
    plugins: [react(), tailwindcss()],
    server: { proxy: { '/api': apiBase || 'http://127.0.0.1:8000' } },
  }
})
