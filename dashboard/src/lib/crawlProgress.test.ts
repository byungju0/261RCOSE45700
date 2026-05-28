import { describe, expect, it } from 'vitest';
import {
  estimatedMinutesToDurationMs,
  formatCrawlRemaining,
  getCrawlProgressSnapshot,
} from './crawlProgress';

describe('crawlProgress', () => {
  it('converts valid estimated minutes to milliseconds', () => {
    expect(estimatedMinutesToDurationMs(2)).toBe(120_000);
  });

  it('falls back to the default duration for invalid estimates', () => {
    expect(estimatedMinutesToDurationMs(0)).toBe(180_000);
    expect(estimatedMinutesToDurationMs(Number.NaN)).toBe(180_000);
  });

  it('calculates bounded percent and remaining time', () => {
    expect(getCrawlProgressSnapshot(1_000, 10_000, 6_000)).toEqual({
      percent: 50,
      remainingMs: 5_000,
      isComplete: false,
    });

    expect(getCrawlProgressSnapshot(1_000, 10_000, 20_000)).toEqual({
      percent: 100,
      remainingMs: 0,
      isComplete: true,
    });
  });

  it('formats remaining time for compact UI labels', () => {
    expect(formatCrawlRemaining(125_000)).toBe('약 3분 남음');
    expect(formatCrawlRemaining(59_000)).toBe('59초 남음');
    expect(formatCrawlRemaining(0)).toBe('완료 확인 중');
  });
});
