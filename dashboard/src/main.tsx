import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import { toast } from 'sonner';
import { registerSW } from 'virtual:pwa-register';
import { Toaster } from '@/components/ui/sonner';
import { GlobalShortcutProvider } from '@/lib/shortcuts';
import { router } from './router';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

// VITE_USE_MOCK=true는 백엔드 없이 정적 데모를 띄우기 위한 빌드 플래그.
// dev에선 항상 MSW 활성, prod 빌드는 이 플래그가 true일 때만 MSW 포함.
const useMock = import.meta.env.VITE_USE_MOCK === 'true';

async function enableMocking() {
  if (!import.meta.env.DEV && !useMock) return;
  const { worker } = await import('./mocks/browser');
  await worker.start({ onUnhandledRequest: 'bypass' });
}

// PWA service worker registration — prod 빌드에서만 active.
// dev에선 MSW가 fetch를 가로채야 하므로 SW 미등록 (vite.config의 devOptions.enabled=false).
// mock 빌드(useMock)에서도 PWA SW와 MSW worker가 동일 scope(`/`)에 등록 충돌하므로 PWA SW 미등록.
function registerPwaUpdateNotifier() {
  const updateSW = registerSW({
    onNeedRefresh() {
      toast.info('새 버전이 있습니다', {
        duration: Infinity,
        action: { label: '업데이트', onClick: () => updateSW(true) },
      });
    },
    onOfflineReady() {
      toast.success('오프라인에서도 사용 가능합니다', { duration: 3000 });
    },
  });
}

if (!useMock) {
  registerPwaUpdateNotifier();
}

enableMocking().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <GlobalShortcutProvider>
          <RouterProvider router={router} />
          <Toaster position="top-right" richColors closeButton />
        </GlobalShortcutProvider>
      </QueryClientProvider>
    </StrictMode>,
  );
});
