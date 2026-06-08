import { queryOptions, useSuspenseQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import { POLLING_QUERY_OPTIONS } from './queryDefaults';
import type { CrawlPipelineStatsResponse, StatsPeriod, StatsResponse } from '@/types/api';

async function fetchStats(period?: StatsPeriod): Promise<StatsResponse> {
  const url = period ? `/stats?period=${period}` : '/stats';
  const response = await apiClient.get<StatsResponse>(url);
  return response.data;
}

export const statsQueries = {
  all: () => ['stats'] as const,
  byPeriod: (period?: StatsPeriod) =>
    queryOptions({
      queryKey: [...statsQueries.all(), { period: period ?? null }] as const,
      queryFn: () => fetchStats(period),
      ...POLLING_QUERY_OPTIONS,
    }),
};

export function useStatsSuspenseQuery(period?: StatsPeriod) {
  return useSuspenseQuery(statsQueries.byPeriod(period));
}

async function fetchCrawlPipelineStats(): Promise<CrawlPipelineStatsResponse> {
  const response = await apiClient.get<CrawlPipelineStatsResponse>('/crawl/stats');
  return response.data;
}

export const crawlStatsQueries = {
  all: () => ['crawlStats'] as const,
  latest: () =>
    queryOptions({
      queryKey: crawlStatsQueries.all(),
      queryFn: fetchCrawlPipelineStats,
      ...POLLING_QUERY_OPTIONS,
    }),
};

export function useCrawlPipelineStatsSuspenseQuery() {
  return useSuspenseQuery(crawlStatsQueries.latest());
}
