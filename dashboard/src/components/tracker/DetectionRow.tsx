import { memo, useEffect, useRef } from 'react';
import { ChevronRight } from 'lucide-react';
import { TableCell, TableRow } from '@/components/ui/table';
import { ConfidenceBadge } from './ConfidenceBadge';
import { TypeIcon } from './TypeIcon';
import { severityOf } from '@/lib/severity';
import { formatRelativeTime } from '@/lib/time';
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
  const severity = severityOf(detection.confidence);

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
        // color-mix tint는 라이트/다크 자동 swap
        'data-[severity=high]:shadow-[inset_6px_0_0_var(--crit-bg)] data-[severity=high]:bg-[color-mix(in_oklch,var(--crit-bg)_8%,transparent)]',
        'data-[severity=medium]:shadow-[inset_6px_0_0_var(--warn-bg)] data-[severity=medium]:bg-[color-mix(in_oklch,var(--warn-bg)_6%,transparent)]',
        // focused는 severity보다 우선
        'data-[focused]:bg-accent data-[focused]:ring-ring/40 data-[focused]:ring-2',
        // visited는 셀 내부에만 — 행 자체 opacity는 ring 대비를 깎음
        '[&[data-visited]_td]:opacity-70',
      )}
    >
      <TableCell className="w-[88px]">
        <ConfidenceBadge score={detection.confidence} />
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
      <TableCell className="text-muted-foreground w-[120px] text-right font-mono text-xs">
        {time}
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
