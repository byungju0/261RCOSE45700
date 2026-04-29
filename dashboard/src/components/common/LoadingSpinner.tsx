import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  label?: string;
  className?: string;
}

const SIZE_CLASS = {
  sm: 'size-4',
  md: 'size-6',
  lg: 'size-8',
} as const;

const TEXT_CLASS = {
  sm: 'text-xs',
  md: 'text-sm',
  lg: 'text-base',
} as const;

export function LoadingSpinner({
  size = 'md',
  label = '로딩 중...',
  className,
}: LoadingSpinnerProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'text-muted-foreground inline-flex items-center gap-2',
        className,
      )}
    >
      <Loader2 className={cn('animate-spin', SIZE_CLASS[size])} aria-hidden />
      <span className={TEXT_CLASS[size]}>{label}</span>
    </div>
  );
}
