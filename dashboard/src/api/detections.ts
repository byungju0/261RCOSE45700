import {
  queryOptions,
  skipToken,
  useMutation,
  useQuery,
  useQueryClient,
  useSuspenseQuery,
} from '@tanstack/react-query';
import { apiClient, ProblemDetailError } from './client';
import { POLLING_QUERY_OPTIONS } from './queryDefaults';
import { statsQueries } from './stats';
import { detectionFilterToParams } from '@/lib/detectionFilter';
import type {
  AgentRun,
  CrawlJobStatusResponse,
  CrawlTriggerResponse,
  Detection,
  DetectionFilter,
  DetectionListResponse,
} from '@/types/api';

async function fetchDetections(
  filter: DetectionFilter,
): Promise<DetectionListResponse> {
  const qs = detectionFilterToParams(filter).toString();
  const response = await apiClient.get<DetectionListResponse>(
    qs ? `/detections?${qs}` : '/detections',
  );
  return response.data;
}

async function fetchDetection(id: number): Promise<Detection> {
  const response = await apiClient.get<Detection>(`/detections/${id}`);
  return response.data;
}

async function fetchAgentRuns(detectionId: number): Promise<AgentRun[]> {
  const response = await apiClient.get<AgentRun[]>(
    `/detections/${detectionId}/agent-runs`,
  );
  return response.data;
}

// TanStack Query v5 queryOptions 팩토리 — 키 일관성 + 같은 파일 hooks에서만 사용.
const detectionQueries = {
  all: () => ['detections'] as const,
  lists: () => [...detectionQueries.all(), 'list'] as const,
  list: (filter: DetectionFilter) =>
    queryOptions({
      queryKey: [...detectionQueries.lists(), filter] as const,
      queryFn: () => fetchDetections(filter),
      ...POLLING_QUERY_OPTIONS,
      placeholderData: (prev) => prev,
    }),
  details: () => [...detectionQueries.all(), 'detail'] as const,
  detail: (id: number) =>
    queryOptions({
      queryKey: [...detectionQueries.details(), id] as const,
      queryFn: () => fetchDetection(id),
      staleTime: 60_000,
    }),
  agentRuns: (id: number | undefined) =>
    queryOptions({
      queryKey: [...detectionQueries.details(), id, 'agent-runs'] as const,
      queryFn: id !== undefined ? () => fetchAgentRuns(id) : skipToken,
      staleTime: 300_000,
    }),
};

export function useDetectionsQuery(filter: DetectionFilter) {
  return useQuery(detectionQueries.list(filter));
}

export function useDetectionsSuspenseQuery(filter: DetectionFilter) {
  return useSuspenseQuery(detectionQueries.list(filter));
}

export function useDetectionQuery(id: number | undefined) {
  return useQuery({
    ...detectionQueries.detail(id ?? 0),
    enabled: id !== undefined && Number.isFinite(id),
  });
}

async function triggerCrawl(): Promise<CrawlTriggerResponse> {
  const response = await apiClient.post<CrawlTriggerResponse>(
    '/crawl/trigger',
    {},
  );
  return response.data;
}

async function fetchCrawlJobStatus(jobId: string): Promise<CrawlJobStatusResponse> {
  try {
    const response = await apiClient.get<CrawlJobStatusResponse>(
      `/crawl/jobs/${jobId}`,
    );
    return response.data;
  } catch (err) {
    // 배포로 컨테이너가 교체되면 Redis TTL 전에 job key가 사라질 수 있음.
    // 404를 throwing하면 useEffect에서 setState를 불러야 하는 패턴이 생기므로
    // failed 상태로 변환해 기존 terminal 처리 흐름(3초 후 jobId 초기화)을 재사용.
    if (err instanceof ProblemDetailError && err.status === 404) {
      return {
        jobId,
        status: 'failed',
        totalSites: 0,
        completedSites: 0,
        percent: 0,
        currentSite: '',
        message: '컨테이너 재시작으로 중단됨',
        failedSites: [],
        requestedAt: '',
        startedAt: '',
        updatedAt: '',
        finishedAt: '',
      };
    }
    throw err;
  }
}

export function useCrawlTriggerMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: triggerCrawl,
    onSuccess: () => {
      // 트리거 후 목록·대시보드 stale 처리 → 다음 폴링에서 갱신
      queryClient.invalidateQueries({ queryKey: detectionQueries.all() });
      queryClient.invalidateQueries({ queryKey: statsQueries.all() });
    },
  });
}

export function useCrawlJobStatusQuery(jobId: string | null) {
  return useQuery({
    queryKey: ['crawl', 'job', jobId],
    queryFn: () => fetchCrawlJobStatus(jobId ?? ''),
    enabled: Boolean(jobId),
    refetchInterval: 2_000,
    staleTime: 1_000,
  });
}

export function useAgentRunsQuery(detectionId: number | undefined) {
  return useQuery(detectionQueries.agentRuns(detectionId));
}
