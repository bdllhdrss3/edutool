import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const apiProxyTarget = process.env.API_PROXY_TARGET
const allowedHosts = process.env.FRONTEND_ALLOWED_HOSTS?.split(',').map((host) => host.trim()).filter(Boolean)

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    allowedHosts: allowedHosts?.length ? allowedHosts : undefined,
    proxy: apiProxyTarget ? { '/api': apiProxyTarget } : undefined,
  },
})
