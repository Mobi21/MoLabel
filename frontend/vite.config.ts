import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'path'

const api = {
  '/api': {
    target: process.env.MOLABEL_API_URL ?? 'http://localhost:8000',
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: { port: 5173, proxy: api },
  preview: { proxy: api },
})
