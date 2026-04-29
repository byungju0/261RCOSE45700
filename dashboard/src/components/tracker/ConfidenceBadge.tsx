import type { HTMLAttributes } from 'react';
import { AlertTriangle, AlertCircle, Circle } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  SEVERITY_LABEL,
  formatScore,
  severityOf,
  type Severity,
} from '@/lib/severity';

interface ConfidenceBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  /** Confidence score 0~1 from VARCO LLM detection */
  score: number;
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
  className,
  ...rest
}: ConfidenceBadgeProps) {
  const level = severityOf(score);
  const Icon = LEVEL_ICON[level];
  const numText = formatScore(score);
  const ariaScore = Number.isFinite(score)
    ? Math.max(0, Math.min(1, score)).toFixed(2)
    : '알 수 없음';

  return (
    <span
      role="status"
      aria-label={`신뢰도 ${ariaScore} (${SEVERITY_LABEL[level]})`}
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
