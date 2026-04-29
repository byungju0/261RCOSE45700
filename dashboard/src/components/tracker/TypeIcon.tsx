import type { LucideIcon } from 'lucide-react';
import { AlertTriangle, Bot, Circle, RefreshCw, ShoppingCart } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { DetectionType } from '@/types/api';
import { getTypeLabel } from './labels';

const ICON_MAP: Record<DetectionType, LucideIcon> = {
  매크로_판매: Bot,
  핵_배포: AlertTriangle,
  계정_거래: ShoppingCart,
  리세마라: RefreshCw,
  기타: Circle,
};

interface TypeIconProps {
  type: DetectionType;
  /** Render icon with text label. Default true for accessibility. */
  showLabel?: boolean;
  className?: string;
}

export function TypeIcon({ type, showLabel = true, className }: TypeIconProps) {
  const Icon = ICON_MAP[type];
  const label = getTypeLabel(type);

  if (!showLabel) {
    return (
      <Icon
        aria-label={label}
        className={cn('text-muted-foreground size-4', className)}
      />
    );
  }

  return (
    <span className={cn('inline-flex items-center gap-1.5 text-sm', className)}>
      <Icon aria-hidden className="text-muted-foreground size-4 shrink-0" />
      <span>{label}</span>
    </span>
  );
}
