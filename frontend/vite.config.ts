import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { normalizeApiBase } from './src/lib/apiConfig'
export default defineConfig(({ mode }) => {
  const fileEnv = loadEnv(mode, process.cwd(), 'VITE_')
  const apiBase = normalizeApiBase(process.env.VITE_API_BASE_URL ?? fileEnv.VITE_API_BASE_URL, mode === 'production')
  return {
    plugins: [react(), tailwindcss()],
    server: { proxy: { '/api': apiBase || 'http://127.0.0.1:8000' } },
  }
})
