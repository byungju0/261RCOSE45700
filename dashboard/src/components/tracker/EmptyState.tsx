import type { ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, FilterX } from 'lucide-react';
import { cn } from '@/lib/utils';

type EmptyVariant = 'healthy' | 'stale' | 'filter-empty';

interface EmptyStateProps {
  variant: EmptyVariant;
  title: string;
  message?: string;
  action?: ReactNode;
  className?: string;
}

const VARIANT_ICON = {
  healthy: CheckCircle2,
  stale: AlertTriangle,
  'filter-empty': FilterX,
} as const;

const VARIANT_ICON_CLASS = {
  healthy: 'text-success',
  stale: 'text-warning',
  'filter-empty': 'text-muted-foreground',
} as const;

export function EmptyState({
  variant,
  title,
  message,
  action,
  className,
}: EmptyStateProps) {
  const Icon = VARIANT_ICON[variant];
  return (
    <section
      role={variant === 'stale' ? 'alert' : 'status'}
      aria-live={variant === 'stale' ? 'assertive' : 'polite'}
      className={cn(
        'bg-card flex flex-col items-center gap-3 rounded-lg border p-12 text-center',
        className,
      )}
    >
      <Icon className={cn('size-8', VARIANT_ICON_CLASS[variant])} aria-hidden />
      <div className="text-foreground text-base font-medium">{title}</div>
      {message && (
        <div className="text-muted-foreground text-xs">{message}</div>
      )}
      {action && <div className="mt-2">{action}</div>}
    </section>
  );
}
