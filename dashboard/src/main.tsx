import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
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
