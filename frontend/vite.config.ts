import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // The FastAPI backend allows this origin (CORS), so keep the port fixed:
    // if 5173 is busy, Vite stops with a clear error instead of moving to a port the API would block.
    port: 5173,
    strictPort: true,
  },
})
