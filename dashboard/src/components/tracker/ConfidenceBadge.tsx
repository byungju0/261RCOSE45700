import type { HTMLAttributes } from 'react';
import { AlertTriangle, AlertCircle, Circle } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  SEVERITY_LABEL,
  formatScore,
  severityOf,
  severityOfDetection,
  severityOfTier,
  type Severity,
} from '@/lib/severity';
import type { Tier } from '@/types/api';

interface ConfidenceBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  /** Confidence score 0~1 from LLM detection */
  score: number;
  /** Detection tier. 전달되면 위험도 색상/아이콘 기준으로 사용. */
  tier?: Tier | string | null;
  /** isIllegal=false(T4)이면 항상 low로 표시. tier 미전달 시 score만으로 판단. */
  isIllegal?: boolean;
}

const LEVEL_CHIP: Record<Severity, string> = {
  high: 'bg-confidence-high-bg text-white',
  medium: 'bg-confidence-medium-bg text-white',
  low: 'border border-border text-muted-foreground',
};

const LEVEL_ICON = {
  high: AlertTriangle,
  medium: AlertCircle,
  low: Circle,
} as const;

export function ConfidenceBadge({
  score,
  tier,
  isIllegal,
  className,
  ...rest
}: ConfidenceBadgeProps) {
  const level =
    isIllegal !== undefined
      ? severityOfDetection({ tier, confidence: score, isIllegal })
      : tier
        ? severityOfTier(tier)
        : severityOf(score);
  const Icon = LEVEL_ICON[level];
  const numText = formatScore(score);
  const ariaScore = Number.isFinite(score)
    ? Math.max(0, Math.min(1, score)).toFixed(2)
    : '알 수 없음';

  return (
    <span
      role="status"
      aria-label={`위험도 ${ariaScore} (${SEVERITY_LABEL[level]})`}
      className={cn(
        'inline-flex size-11 flex-col items-center justify-center gap-[3px] rounded-md font-mono leading-none',
        LEVEL_CHIP[level],
        className,
      )}
      {...rest}
    >
      <Icon
        aria-hidden
        className={cn('shrink-0', level === 'low' ? 'size-2.5' : 'size-[13px]')}
        strokeWidth={2.5}
      />
      <span className="text-[13px] font-bold tabular-nums tracking-tight">
        {numText}
      </span>
    </span>
  );
}
