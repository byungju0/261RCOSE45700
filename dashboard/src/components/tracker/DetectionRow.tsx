import { memo, useEffect, useRef } from 'react';
import { ChevronRight } from 'lucide-react';
import { TableCell, TableRow } from '@/components/ui/table';
import { ConfidenceBadge } from './ConfidenceBadge';
import { TypeIcon } from './TypeIcon';
import { SEVERITY_TINT_CLASSES, severityOfDetection } from '@/lib/severity';
import { formatDateTime, formatRelativeTime } from '@/lib/time';
import { cn } from '@/lib/utils';
import type { Detection } from '@/types/api';

interface DetectionRowProps {
  detection: Detection;
  /** Currently focused via j/k navigation. Auto-scrolls into view. */
  focused?: boolean;
  /** Already visited in this session. Renders muted. */
  visited?: boolean;
  onSelect: () => void;
}

function DetectionRowImpl({
  detection,
  focused = false,
  visited = false,
  onSelect,
}: DetectionRowProps) {
  const ref = useRef<HTMLTableRowElement | null>(null);

  useEffect(() => {
    if (focused && ref.current) {
      ref.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [focused]);

  const time = formatRelativeTime(detection.detectedAt);
  const dateTime = formatDateTime(detection.detectedAt);
  const severity = severityOfDetection(detection);

  return (
    <TableRow
      ref={ref}
      role="row"
      tabIndex={0}
      aria-selected={focused}
      data-focused={focused || undefined}
      data-visited={visited || undefined}
      data-severity={severity}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          onSelect();
        }
      }}
      className={cn(
        'cursor-pointer',
        SEVERITY_TINT_CLASSES,
        // focused는 severity보다 우선 — 키보드 네비 시만 표시, 중성 surface로
        'data-[focused]:bg-secondary data-[focused]:ring-1 data-[focused]:ring-border',
        // visited는 셀 내부에만 — 행 자체 opacity는 ring 대비를 깎음
        '[&[data-visited]_td]:opacity-70',
      )}
    >
      <TableCell className="w-[88px]">
        <ConfidenceBadge score={detection.confidence} tier={detection.tier} isIllegal={detection.isIllegal} />
      </TableCell>
      <TableCell className="w-[170px]">
        <TypeIcon type={detection.type} />
      </TableCell>
      <TableCell className="text-muted-foreground w-[180px] font-mono text-xs">
        {detection.siteName}
      </TableCell>
      <TableCell className="text-muted-foreground max-w-0 truncate text-sm">
        {detection.translatedText ?? detection.rawText}
      </TableCell>
      <TableCell
        className="text-muted-foreground w-[132px] text-right font-mono text-xs"
        title={time}
      >
        {dateTime}
      </TableCell>
      <TableCell className="w-[40px] text-right">
        <ChevronRight
          className="text-muted-foreground inline-block size-4"
          aria-hidden
        />
      </TableCell>
    </TableRow>
  );
}

/**
 * placeholderData: prev 덕분에 detection 객체 참조가 안정적 — 폴링 시 변하지 않은
 * 행은 memo로 re-render 차단.
 */
export const DetectionRow = memo(DetectionRowImpl);
