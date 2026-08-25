import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Expose the development server to VS Code's forwarded browser port.
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        // Use IPv4 explicitly: the backend is published on the local IPv4 interface.
        target: 'http://127.0.0.1:8080',
        timeout: 600000,
        proxyTimeout: 600000,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, request) => {
            console.info(`[vite proxy] ${request.method} ${request.url} -> ${proxyReq.protocol}//${proxyReq.host}${proxyReq.path}`)
          })
          proxy.on('proxyRes', (proxyRes, request) => {
            console.info(`[vite proxy] ${request.method} ${request.url} <- ${proxyRes.statusCode} (${proxyRes.headers['content-length'] ?? 'stream'} bytes)`)
            if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache';
              proxyRes.headers['connection'] = 'keep-alive';
              proxyRes.headers['x-accel-buffering'] = 'no';
            }
          })
          proxy.on('error', (error, request) => {
            console.error(`[vite proxy] ${request.method} ${request.url} failed: ${error.message}`)
          })
        },
      },
    },
  },
})
