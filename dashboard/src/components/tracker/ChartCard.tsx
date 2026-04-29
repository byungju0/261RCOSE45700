import type { ReactNode } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

interface ChartCardProps {
  title: string;
  subtitle?: string;
  loading?: boolean;
  empty?: boolean;
  emptyMessage?: string;
  children: ReactNode;
  className?: string;
}

export function ChartCard({
  title,
  subtitle,
  loading = false,
  empty = false,
  emptyMessage = '표시할 데이터가 없습니다',
  children,
  className,
}: ChartCardProps) {
  return (
    <Card className={cn('flex flex-col', className)}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold">{title}</CardTitle>
        {subtitle && (
          <div className="text-muted-foreground text-xs">{subtitle}</div>
        )}
      </CardHeader>
      <CardContent className="flex flex-1 items-center justify-center">
        {loading ? (
          <Skeleton className="h-[260px] w-full" />
        ) : empty ? (
          <div className="text-muted-foreground flex h-[260px] w-full items-center justify-center text-sm">
            {emptyMessage}
          </div>
        ) : (
          <div className="w-full">{children}</div>
        )}
      </CardContent>
    </Card>
  );
}
