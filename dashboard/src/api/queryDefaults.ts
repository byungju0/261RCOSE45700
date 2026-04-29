/** 60s 자동 폴링 + 30s staleTime — Tracker 운영 도구 표준. */
export const POLLING_QUERY_OPTIONS = {
  refetchInterval: 60_000,
  staleTime: 30_000,
} as const;
