/// <reference types="vitest/config" />
import { unlinkSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig, type PluginOption } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/**
 * MSW worker(`public/mockServiceWorker.js`)는 dev 전용이지만 vite는 `public/` 자산을
 * 자동으로 dist/에 복사 → production에서 dev-only worker가 공개 경로에 노출됨.
 * build closeBundle 훅에서 실제 파일을 제거해 dist/에 흔적이 안 남도록 한다.
 *
 * 단 VITE_USE_MOCK=true 빌드는 의도적으로 MSW를 prod에 포함하는 데모 모드 →
 * worker 파일을 dist/에 보존해 클라이언트에서 MSW가 정상 등록되도록 한다.
 */
const removeDevMswWorker = (): PluginOption => ({
  name: 'tracker:remove-dev-msw-worker',
  apply: 'build',
  closeBundle: {
    order: 'pre',
    handler() {
      if (process.env.VITE_USE_MOCK === 'true') return;
      try {
        unlinkSync(fileURLToPath(new URL('./dist/mockServiceWorker.js', import.meta.url)))
      } catch {
        // 파일이 이미 없으면 무시 (다른 빌드 환경 호환).
      }
    },
  },
})

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    removeDevMswWorker(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    // 무거운 vendor를 별 chunk로 분리 — 캐싱 친화 + route lazy split의 효과 극대화.
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('recharts')) return 'recharts';
            if (id.includes('radix-ui') || id.includes('@radix-ui')) return 'radix';
            if (id.includes('@tanstack')) return 'tanstack';
            if (id.includes('date-fns')) return 'date-fns';
          }
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    css: false,
    // Playwright e2e specs는 vitest 대상에서 제외 — playwright test 명령으로 별도 실행.
    exclude: ['node_modules', 'dist', 'e2e/**'],
  },
})
