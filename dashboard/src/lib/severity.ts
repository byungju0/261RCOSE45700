/**
 * Severity threshold + display 표준 — confidence([0,1])를 high/medium/low로 매핑.
 * ConfidenceBadge / DetectionRow / RecentAlertList 등에서 동일 룰 공유.
 */

export type Severity = 'high' | 'medium' | 'low';

export const SEVERITY_LABEL: Record<Severity, string> = {
  high: '높음',
  medium: '중간',
  low: '낮음',
};

export function severityOf(score: number): Severity {
  if (!Number.isFinite(score)) return 'low';
  const s = Math.max(0, Math.min(1, score));
  if (s >= 0.8) return 'high';
  if (s >= 0.5) return 'medium';
  return 'low';
}

/** 0.95 → ".95" — 44px 칩 너비에 맞춤. 1.00은 0.99로 캡(폭 보호). NaN은 "—". */
export function formatScore(score: number): string {
  if (!Number.isFinite(score)) return '—';
  const s = Math.max(0, Math.min(0.99, score));
  return s.toFixed(2).replace(/^0/, '');
}
