import { useQuery } from '@tanstack/react-query';
import { apiClient } from './client';
import { POLLING_QUERY_OPTIONS } from './queryDefaults';
import type { StatsPeriod, StatsResponse } from '@/types/api';

export const STATS_QUERY_KEY = 'stats' as const;

async function fetchStats(period?: StatsPeriod): Promise<StatsResponse> {
  const url = period ? `/stats?period=${period}` : '/stats';
  const response = await apiClient.get<StatsResponse>(url);
  return response.data;
}

export function useStatsQuery(period?: StatsPeriod) {
  return useQuery({
    queryKey: [STATS_QUERY_KEY, { period: period ?? null }],
    queryFn: () => fetchStats(period),
    ...POLLING_QUERY_OPTIONS,
  });
}
