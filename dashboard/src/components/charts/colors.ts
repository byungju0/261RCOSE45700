import type { DetectionType } from '@/types/api';

/**
 * Tracker chart palette — 식별 전용 색 (UX Spec Step 8).
 * 의미적 위계 없이 채도/명도가 비슷하게 설계됨. 위험 시그널은 confidence 색상이 담당.
 *
 * CSS 변수(`--chart-1`~`--chart-5`)를 가리키는 wrapper 함수.
 * Recharts는 prop으로 색을 받기 때문에 hsl() 함수처럼 직접 변수 참조 불가.
 * → 런타임에 computed style에서 토큰 값을 읽어와 주입.
 *
 * 매핑은 UX Spec Step 8과 일치:
 * - chart-1 violet  → 매크로_판매
 * - chart-2 blue    → 핵_배포
 * - chart-3 teal    → 계정_거래
 * - chart-4 orange  → 리세마라
 * - chart-5 zinc    → 기타
 */

const TYPE_TO_CHART_VAR: Record<DetectionType, string> = {
  매크로_판매: '--chart-1',
  핵_배포: '--chart-2',
  계정_거래: '--chart-3',
  리세마라: '--chart-4',
  기타: '--chart-5',
};

/**
 * CSS 변수 reference. Recharts는 fill prop에 `var(--chart-1)` 같은
 * CSS 함수를 직접 받지 못하지만, `hsl(var(--x))` 같은 wrapper나
 * `oklch()` 직접 값은 받음. CSS variable 참조 문자열을 반환.
 */
export function colorForType(type: DetectionType): string {
  return `var(${TYPE_TO_CHART_VAR[type]})`;
}

export const CHART_PALETTE_VARS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
] as const;
