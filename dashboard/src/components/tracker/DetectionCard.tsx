import { ChevronRight } from 'lucide-react';
import { ConfidenceBadge } from './ConfidenceBadge';
import { TypeIcon } from './TypeIcon';
import { SEVERITY_TINT_CLASSES, severityOfDetection } from '@/lib/severity';
import { formatDateTime, formatRelativeTime } from '@/lib/time';
import { cn } from '@/lib/utils';
import type { Detection } from '@/types/api';

interface DetectionCardProps {
  detection: Detection;
  visited?: boolean;
  onSelect: () => void;
}

/**
 * 모바일(< md) 전용 카드 행 — DetectionList Table 대체.
 * 데스크탑은 `<DetectionRow>` (TableRow 기반) 사용.
 */
export function DetectionCard({ detection, visited = false, onSelect }: DetectionCardProps) {
  const severity = severityOfDetection(detection);
  const time = formatRelativeTime(detection.detectedAt);
  const dateTime = formatDateTime(detection.detectedAt);
  const snippet = detection.translatedText ?? detection.rawText;

  return (
    <button
      type="button"
      onClick={onSelect}
      data-severity={severity}
      data-visited={visited || undefined}
      aria-label={`탐지 상세 열기 — ${detection.type}, ${detection.siteName}`}
      className={cn(
        'block w-full cursor-pointer border-b bg-transparent text-left transition-colors last:border-b-0',
        'hover:bg-[var(--hover)] active:bg-[var(--active)]',
        SEVERITY_TINT_CLASSES,
        'data-[visited]:opacity-70',
      )}
      style={{ borderColor: 'var(--border-1)' }}
    >
      <div className="flex flex-col gap-1.5 px-4 py-3">
        <div className="flex items-center gap-2.5">
          <ConfidenceBadge score={detection.confidence} tier={detection.tier} isIllegal={detection.isIllegal} aria-hidden />
          <TypeIcon type={detection.type} />
          <ChevronRight
            className="text-muted-foreground ml-auto size-4 shrink-0"
            aria-hidden
          />
        </div>
        <div className="flex items-baseline justify-between gap-2">
          <span
            className="text-fg-3 font-mono text-xs"
            style={{ fontFeatureSettings: "'liga' off" }}
          >
            {detection.siteName}
          </span>
          <span className="text-fg-3 font-mono text-xs tabular-nums" title={time}>
            {dateTime}
          </span>
        </div>
        <p
          className="text-fg-2 line-clamp-2 text-sm leading-relaxed"
          style={{ fontSize: 'var(--size-alert-snippet)' }}
        >
          {snippet}
        </p>
      </div>
    </button>
  );
}
