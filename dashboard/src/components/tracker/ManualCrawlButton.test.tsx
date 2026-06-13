import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { GlobalShortcutProvider } from '@/lib/shortcuts';
import { ManualCrawlButton } from './ManualCrawlButton';

function renderWithQueryClient() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <GlobalShortcutProvider>
        <ManualCrawlButton />
      </GlobalShortcutProvider>
    </QueryClientProvider>,
  );
}

describe('ManualCrawlButton', () => {
  afterEach(() => {
    vi.useRealTimers();
    sessionStorage.clear();
  });

  it('keeps showing progress while the server job is still running', async () => {
    sessionStorage.setItem('crawl:jobId', 'mock-crawl-job');
    sessionStorage.setItem(
      'crawl:progressWindow',
      JSON.stringify({
        startedAtMs: Date.now() - 60 * 60 * 1000,
        durationMs: 1,
      }),
    );

    renderWithQueryClient();

    expect(await screen.findByText('크롤링 중')).toBeInTheDocument();
    expect(await screen.findByText(/38% · bahamut 처리 중/)).toBeInTheDocument();

    vi.useFakeTimers();
    act(() => {
      vi.advanceTimersByTime(10_000);
    });

    expect(screen.getByText('크롤링 중')).toBeInTheDocument();
    expect(screen.getByText(/38% · bahamut 처리 중/)).toBeInTheDocument();
    expect(sessionStorage.getItem('crawl:jobId')).toBe('mock-crawl-job');
  });
});
