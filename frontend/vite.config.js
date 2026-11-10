import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server on 5190; API calls and the WebSocket are proxied to FastAPI on 8100.
// `npm run build` writes dist/, which FastAPI then serves on 8100 by itself.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5190,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8100',
      '/ws': { target: 'ws://127.0.0.1:8100', ws: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
