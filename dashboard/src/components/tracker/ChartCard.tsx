import type { ReactNode } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface ChartCardProps {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  empty?: boolean;
  emptyMessage?: string;
  children: ReactNode;
  className?: string;
}

export function ChartCard({
  title,
  subtitle,
  action,
  empty = false,
  emptyMessage = '표시할 데이터가 없습니다',
  children,
  className,
}: ChartCardProps) {
  return (
    <Card className={cn('@container/chart flex flex-col', className)}>
      {(title || subtitle || action) && (
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              {title && <CardTitle className="text-sm font-semibold">{title}</CardTitle>}
              {subtitle && (
                <div className="text-muted-foreground text-xs">{subtitle}</div>
              )}
            </div>
            {action && <div className="shrink-0">{action}</div>}
          </div>
        </CardHeader>
      )}
      <CardContent className="flex flex-1 items-center justify-center">
        {empty ? (
          <div className="text-muted-foreground flex h-[200px] w-full items-center justify-center text-sm @md/chart:h-[260px]">
            {emptyMessage}
          </div>
        ) : (
          <div className="w-full">{children}</div>
        )}
      </CardContent>
    </Card>
  );
}
