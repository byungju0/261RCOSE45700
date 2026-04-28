import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from './client';
import { POLLING_QUERY_OPTIONS } from './queryDefaults';
import { detectionFilterToParams } from '@/lib/detectionFilter';
import type {
  CrawlTriggerResponse,
  Detection,
  DetectionFilter,
  DetectionListResponse,
} from '@/types/api';

export const DETECTIONS_QUERY_KEY = 'detections' as const;

async function fetchDetections(
  filter: DetectionFilter,
): Promise<DetectionListResponse> {
  const qs = detectionFilterToParams(filter).toString();
  const response = await apiClient.get<DetectionListResponse>(
    qs ? `/detections?${qs}` : '/detections',
  );
  return response.data;
}

export function useDetectionsQuery(filter: DetectionFilter) {
  return useQuery({
    queryKey: [DETECTIONS_QUERY_KEY, 'list', filter],
    queryFn: () => fetchDetections(filter),
    ...POLLING_QUERY_OPTIONS,
    placeholderData: (prev) => prev,
  });
}

async function fetchDetection(id: number): Promise<Detection> {
  const response = await apiClient.get<Detection>(`/detections/${id}`);
  return response.data;
}

export function useDetectionQuery(id: number | undefined) {
  return useQuery({
    queryKey: [DETECTIONS_QUERY_KEY, 'detail', id],
    queryFn: () => fetchDetection(id as number),
    enabled: id !== undefined && Number.isFinite(id),
    staleTime: 60_000,
  });
}

async function triggerCrawl(): Promise<CrawlTriggerResponse> {
  const response = await apiClient.post<CrawlTriggerResponse>(
    '/crawl/trigger',
    {},
  );
  return response.data;
}

export function useCrawlTriggerMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: triggerCrawl,
    onSuccess: () => {
      // 트리거 후 목록·통계 stale 처리 → 다음 폴링에서 갱신
      queryClient.invalidateQueries({ queryKey: [DETECTIONS_QUERY_KEY] });
      queryClient.invalidateQueries({ queryKey: ['stats'] });
    },
  });
}
