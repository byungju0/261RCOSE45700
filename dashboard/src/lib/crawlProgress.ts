export const DEFAULT_CRAWL_ESTIMATE_MINUTES = 3;

export interface CrawlProgressSnapshot {
  percent: number;
  remainingMs: number;
  isComplete: boolean;
}

export function estimatedMinutesToDurationMs(minutes: number): number {
  if (!Number.isFinite(minutes) || minutes <= 0) {
    return DEFAULT_CRAWL_ESTIMATE_MINUTES * 60_000;
  }
  return minutes * 60_000;
}

export function getCrawlProgressSnapshot(
  startedAtMs: number,
  durationMs: number,
  nowMs: number,
): CrawlProgressSnapshot {
  const safeDurationMs = Math.max(durationMs, 1);
  const elapsedMs = Math.max(0, nowMs - startedAtMs);
  const remainingMs = Math.max(0, safeDurationMs - elapsedMs);
  const percent = Math.min(100, Math.round((elapsedMs / safeDurationMs) * 100));

  return {
    percent,
    remainingMs,
    isComplete: remainingMs === 0,
  };
}

export function formatCrawlRemaining(remainingMs: number): string {
  const remainingSeconds = Math.ceil(Math.max(0, remainingMs) / 1000);

  if (remainingSeconds <= 0) return '완료 확인 중';
  if (remainingSeconds < 60) return `${remainingSeconds}초 남음`;

  return `약 ${Math.ceil(remainingSeconds / 60)}분 남음`;
}
