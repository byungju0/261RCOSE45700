/**
 * Severity display 표준 — detection tier를 high/medium/low로 매핑.
 * ConfidenceBadge / DetectionRow / RecentAlertList 등에서 동일 룰 공유.
 */

import type { Tier } from '@/types/api';

export type Severity = 'high' | 'medium' | 'low';

export const SEVERITY_LABEL: Record<Severity, string> = {
  high: '높음',
  medium: '중간',
  low: '낮음',
};

/**
 * `data-severity` attribute 기반 tint 클래스 — high/medium에 좌측 6px 칩 + 옅은 배경.
 * color-mix는 oklch라 라이트/다크 자동 swap. DetectionRow / DetectionCard /
 * RecentAlertList AlertRow에서 공유.
 */
export const SEVERITY_TINT_CLASSES =
  'data-[severity=high]:shadow-[inset_6px_0_0_var(--crit-bg)] data-[severity=high]:bg-[color-mix(in_oklch,var(--crit-bg)_8%,transparent)] data-[severity=medium]:shadow-[inset_6px_0_0_var(--warn-bg)] data-[severity=medium]:bg-[color-mix(in_oklch,var(--warn-bg)_6%,transparent)]';

export function severityOf(score: number): Severity {
  if (!Number.isFinite(score)) return 'low';
  const s = Math.max(0, Math.min(1, score));
  if (s >= 0.8) return 'high';
  if (s >= 0.5) return 'medium';
  return 'low';
}

export function severityOfTier(tier: Tier | string | null | undefined): Severity {
  if (tier === 'T1') return 'high';
  if (tier === 'T2') return 'medium';
  return 'low';
}

/** isIllegal=false(T4 기타)이면 tier와 무관하게 low — 합법 게시글에 경고 배지 방지. */
export function severityOfDetection(d: {
  tier?: Tier | string | null;
  confidence?: number;
  isIllegal: boolean;
}): Severity {
  if (!d.isIllegal) return 'low';
  if (!d.tier && d.confidence !== undefined) return severityOf(d.confidence);
  return severityOfTier(d.tier);
}

/** 0.95 → ".95" — 44px 칩 너비에 맞춤. 1.00은 0.99로 캡(폭 보호). NaN은 "—". */
export function formatScore(score: number): string {
  if (!Number.isFinite(score)) return '—';
  const s = Math.max(0, Math.min(0.99, score));
  return s.toFixed(2).replace(/^0/, '');
}

/**
 * Tier 우선 위험도 점수 — 숫자가 높을수록 실제로 위험.
 * T1: 0.85~1.00 / T2: 0.65~0.80 / T3: 0.45~0.60
 * Tier 내에서는 confidence가 높을수록 올라가되, T1은 항상 T2보다 높음.
 */
export function riskScore(
  confidence: number,
  tier: Tier | string | null | undefined,
): number {
  const c = Math.max(0, Math.min(1, Number.isFinite(confidence) ? confidence : 0));
  if (tier === 'T1') return 0.85 + c * 0.15;
  if (tier === 'T2') return 0.65 + c * 0.15;
  if (tier === 'T3') return 0.45 + c * 0.15;
  return c;
}
