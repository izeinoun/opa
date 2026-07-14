import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    // Bind all interfaces so the dev server is reachable over the box's public
    // hostname (EC2), not just loopback.
    host: true,
    // Vite 5.4 rejects requests whose Host header isn't in this list; allow the
    // EC2 public DNS (and any host) so remote browsers aren't "Blocked".
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
    },
  },
})
