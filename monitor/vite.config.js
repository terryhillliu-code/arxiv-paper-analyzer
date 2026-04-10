import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 8897,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8898',
        changeOrigin: true,
      }
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          // React 核心库
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          // 图表库 (最大的依赖)
          'recharts': ['recharts'],
          // 工具库
          'utils': ['date-fns', 'lucide-react'],
        }
      }
    },
    // 提高块大小警告阈值
    chunkSizeWarningLimit: 600,
  }
})